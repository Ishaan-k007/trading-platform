#include "trading_service.hpp"
TradingServiceImplementation::TradingServiceImplementation(PriceStore* price_store, UserStateStore* user_store, WALWriter* wal_writer , OrderBook* order_book)
    : price_store(price_store), user_store(user_store), wal_writer(wal_writer), order_book(order_book)
{};

grpc::Status TradingServiceImplementation::CheckOrder(grpc::ServerContext* ctx, const trading::CheckOrderRequest* request, trading::CheckOrderResponse* response){
    double bid, ask;

    auto ob_bid = order_book->best_bid(request->symbol());
    auto ob_ask = order_book->best_ask(request->symbol());
    if (ob_bid.has_value() && ob_ask.has_value()) {
        bid = ob_bid.value();
        ask = ob_ask.value();
    }
    else {
        auto symbol_data = price_store->get_symbol_data(request->symbol());
        if (!symbol_data.has_value()) {
            response->set_approved(false);
            response->set_reason("Unknown Symbol");
            return grpc::Status::OK;
        }
        bid = symbol_data.value().price;
        ask = symbol_data.value().price;
    }

    double fill_price = 0.0;
    if (request->order_type() == "MARKET") {
        fill_price = (request->side() == "BUY") ? ask : bid;
    }

    if (request->order_type() == "LIMIT") {
        if(request->side() == "BUY" && request->limit_price() >= ask) {
            fill_price = ask;
        }
        else if(request->side() == "SELL" && request->limit_price() <= bid) {
            fill_price = bid;
        }
        else {
            response->set_approved(false);
            response->set_reason("Limit price not met");
            return grpc::Status::OK;
        }

    }

    ReservationResult approved = user_store->check_and_reserve_position(request->user_id(),request->side(),request->symbol(),request->quantity(),fill_price);
    if (!approved.success) {
        response->set_approved(false);
        response->set_reason("Insufficient funds or position");
        return grpc::Status::OK;
    }
    else {
        response->set_approved(true);
        response->set_reason("Order approved");
        response->set_new_cash_balance(approved.new_cash);
        response->set_new_quantity(approved.new_quantity);
        response->set_new_average_price(approved.new_average_price);
        response->set_fill_price(fill_price);
        return grpc::Status::OK;
    }


}


grpc::Status TradingServiceImplementation::UpdateState(grpc::ServerContext* ctx, const trading::UpdateStateRequest* request, trading::UpdateStateResponse* response) {
    wal_writer->write_fill(
        request->user_id(), request->order_id(), request->symbol(),
        request->side(), request->order_type(),
        request->quantity(), request->fill_price(),
        request->new_cash_balance(), request->new_quantity(), request->new_average_price()
    );
    response->set_success(true);
    response->set_message("State updated");
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

