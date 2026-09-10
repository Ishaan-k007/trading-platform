#include "trading_service.hpp"
#include <cmath>

TradingServiceImplementation::TradingServiceImplementation(PriceStore* price_store, UserStateStore* user_store, WALWriter* wal_writer , OrderBook* order_book)
    : price_store(price_store), user_store(user_store), wal_writer(wal_writer), order_book(order_book)
{};


grpc::Status TradingServiceImplementation::ExecuteOrder(
        grpc::ServerContext* ctx, const trading::ExecuteOrderRequest* request,
        trading::ExecuteOrderResponse* response) {

    response->set_client_order_id(request->client_order_id());
    const std::string& side = request->side();
    const std::string& type = request->order_type();

    // (1) reject malformed requests before touching any state
    if (request->client_order_id().empty()
        || (side != "BUY" && side != "SELL")
        || (type != "MARKET" && type != "LIMIT")
        || !(request->quantity() > 0.0) || !std::isfinite(request->quantity())
        || (type == "LIMIT" && !std::isfinite(request->limit_price()))) {
        response->set_result(trading::INVALID_ORDER);
        response->set_message("malformed order");
        return grpc::Status::OK;
    }

    // (2) price the order: prefer the live order book, fall back to price store
    double bid, ask;
    auto ob_bid = order_book->best_bid(request->symbol());
    auto ob_ask = order_book->best_ask(request->symbol());
    if (ob_bid.has_value() && ob_ask.has_value()) {
        bid = *ob_bid;
        ask = *ob_ask;
    } else {
        auto sd = price_store->get_symbol_data(request->symbol());
        if (!sd.has_value()) {
            response->set_result(trading::UNKNOWN_SYMBOL);
            response->set_message("unknown symbol");
            return grpc::Status::OK;
        }
        bid = sd->price;
        ask = sd->price;
    }
    response->set_market_price((bid + ask) / 2.0);

    double fill_price;
    if (type == "MARKET") {
        fill_price = (side == "BUY") ? ask : bid;
    } else {
        if (side == "BUY" && request->limit_price() >= ask) {
            fill_price = ask;
        } else if (side == "SELL" && request->limit_price() <= bid) {
            fill_price = bid;
        } else {
            response->set_result(trading::LIMIT_NOT_MET);
            response->set_message("limit price not met");
            return grpc::Status::OK;
        }
    }

    // (3) hand off to the atomic execute
    ExecuteResult r = user_store->execute_order(
        request->user_id(), request->client_order_id(), side,
        request->symbol(), request->quantity(), fill_price,
        wal_writer, type);

    response->set_order_id(r.order_id);
    response->set_event_id(r.event_id);
    response->set_account_sequence(r.account_sequence);

    // (4) translate the engine's ExecOutcome into the protobuf result code
    switch (r.outcome) {
        case ExecOutcome::Filled:
            response->set_result(trading::FILLED);
            response->set_fill_price(r.fill_price);
            response->set_new_cash(r.new_cash);
            response->set_new_quantity(r.new_quantity);
            response->set_message(r.from_cache ? "idempotent replay" : "filled");
            break;
        case ExecOutcome::InsufficientFunds:
            response->set_result(trading::INSUFFICIENT_FUNDS);
            response->set_required_cash(r.required_cash);
            response->set_available_cash(r.available_cash);
            response->set_message("insufficient funds");
            break;
        case ExecOutcome::InsufficientPosition:
            response->set_result(trading::INSUFFICIENT_POSITION);
            response->set_required_quantity(r.required_quantity);
            response->set_available_quantity(r.available_quantity);
            response->set_message("insufficient position");
            break;
        case ExecOutcome::IdempotencyConflict:
            response->set_result(trading::IDEMPOTENCY_CONFLICT);
            response->set_message("client_order_id reused with different parameters");
            break;
        default:
            response->set_result(trading::INVALID_ORDER);
            response->set_message("invalid order");
            break;
    }
    return grpc::Status::OK;
}



grpc::Status TradingServiceImplementation::LoadUser(grpc::ServerContext* ctx, const trading::LoadUserRequest* request, trading::LoadUserResponse* response){
    std::vector<std::pair<std::string, PositionState>> positions;
    for (const auto& pos : request->positions()) {
            PositionState ps;
            ps.quantity = pos.quantity();
            ps.average_price = pos.average_price();
            positions.push_back({pos.symbol(), ps});

    }
    user_store->load_user(request->user_id(), request->cash_balance(), positions);


    response->set_success(true);
    response->set_message("User loaded");
    return grpc::Status::OK;

}

grpc::Status TradingServiceImplementation::GetPrice(grpc::ServerContext* ctx, const trading::GetPriceRequest* request, trading::GetPriceResponse* response){
    auto ob_bid = order_book->best_bid(request->symbol());
    auto ob_ask = order_book->best_ask(request->symbol());

    if (ob_bid.has_value() && ob_ask.has_value()) {
        auto ts = order_book->updated_at(request->symbol());

        response->set_symbol(request->symbol());
        response->set_best_bid(ob_bid.value());
        response->set_best_ask(ob_ask.value());
        response->set_price((ob_bid.value() + ob_ask.value()) / 2.0);
        response->set_updated_at(ts.value_or(""));

        return grpc::Status::OK;
    }

    auto symbol_data = price_store->get_symbol_data(request->symbol());
    if (!symbol_data.has_value()) {
        return grpc::Status(grpc::StatusCode::NOT_FOUND, "Symbol not found");
    }

    response->set_symbol(request->symbol());
    response->set_best_bid(symbol_data.value().price);
    response->set_best_ask(symbol_data.value().price);
    response->set_price(symbol_data.value().price);
    response->set_updated_at(symbol_data.value().updated_at);

    return grpc::Status::OK;
}

grpc::Status TradingServiceImplementation::GetAllPrices(grpc::ServerContext* ctx, const trading::GetAllPricesRequest* request, trading::GetAllPricesResponse* response){
    auto all_prices = price_store->get_all();
    for (const auto& [symbol, price] : all_prices) {
    (*response->mutable_prices())[symbol] = price;
    }


    return grpc::Status::OK;
}

grpc::Status TradingServiceImplementation::HasUser(grpc::ServerContext* ctx, const trading::HasUserRequest* request, trading::HasUserResponse* response) {
    response->set_loaded(user_store->has_user(request->user_id()));
    return grpc::Status::OK;
}

grpc::Status TradingServiceImplementation::UpdateOrderBook(grpc::ServerContext* ctx, const trading::OrderBookUpdateRequest* request, trading::OrderBookUpdateResponse* response) {
    std::vector<PriceLevel> bids;
    for (const auto& level : request->bids()) {
        PriceLevel l;
        l.price = level.price();
        l.quantity = level.quantity();
        bids.push_back(l);
    }

    std::vector<PriceLevel> asks;
    for (const auto& level : request->asks()) {
        PriceLevel l;
        l.price = level.price();
        l.quantity = level.quantity();
        asks.push_back(l);
    }

    order_book->update(request->symbol(), bids, asks, request->updated_at());

    response->set_success(true);
    return grpc::Status::OK;
}

