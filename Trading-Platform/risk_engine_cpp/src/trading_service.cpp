#include "trading_service.hpp"

TradingServiceImplementation::TradingServiceImplementation(PriceStore* price_store, UserStateStore* user_store, WALWriter* wal_writer)
    : price_store(price_store), user_store(user_store), wal_writer(wal_writer)
{};

grpc::Status TradingServiceImplementation::CheckOrder(grpc::ServerContext* ctx, const trading::CheckOrderRequest* request, trading::CheckOrderResponse* response){
    auto symbol_data = price_store->get_symbol_data(request->symbol());
    if (!symbol_data.has_value()) {
        response->set_approved(false);
        response->set_reason("Unknown Symbol");
        return grpc::Status::OK;
    }

    double fill_price = 0.0;
    if (request->order_type() == "MARKET") {
        fill_price = symbol_data.value().price;
    }

    if (request->order_type() == "LIMIT") {
        if(request->side() == "BUY" && request->limit_price() >= symbol_data.value().price) {
            fill_price = symbol_data.value().price;
        }
        else if(request->side() == "SELL" && request->limit_price() <= symbol_data.value().price) {
            fill_price = symbol_data.value().price;
        }
        else {
            response->set_approved(false);
            response->set_reason("Limit price not met");
            return grpc::Status::OK;
        }
        
    }

    bool approved = user_store->check_and_reserve_position(request->user_id(),request->side(),request->symbol(),request->quantity(),fill_price);
    if (!approved) {
        response->set_approved(false);
        response->set_reason("Insufficient funds or position");
        return grpc::Status::OK;
    }
    else {
        response->set_approved(true);
        response->set_fill_price(fill_price);
        return grpc::Status::OK;
    }


}


grpc::Status TradingServiceImplementation::UpdateState(grpc::ServerContext* ctx, const trading::UpdateStateRequest* request, trading::UpdateStateResponse* response) {
    user_store->update_position(
        request->user_id(), request->symbol(),
        request->new_cash_balance(), request->new_quantity(), request->new_average_price()
    );
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
    auto symbol_data = price_store->get_symbol_data(request->symbol());
    if (!symbol_data.has_value()) {
        return grpc::Status(grpc::StatusCode::NOT_FOUND, "Symbol not found");

    }

    
    response->set_symbol(request->symbol());

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

