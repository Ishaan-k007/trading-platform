#pragma once
#include "trading.grpc.pb.h"
#include <grpcpp/grpcpp.h>
#include "price_store.hpp"
#include "user_state_store.hpp"
#include "wal_writer.hpp"

class TradingServiceImplementation : public trading::TradingService::Service {
public:
    TradingServiceImplementation(PriceStore* price_store, UserStateStore* user_store, WALWriter* wal_writer);

    grpc::Status CheckOrder(grpc::ServerContext* ctx, const trading::CheckOrderRequest* request, trading::CheckOrderResponse* response) override;
    grpc::Status UpdateState(grpc::ServerContext* ctx, const trading::UpdateStateRequest* request, trading::UpdateStateResponse* response) override;
    grpc::Status LoadUser(grpc::ServerContext* ctx, const trading::LoadUserRequest* request, trading::LoadUserResponse* response) override;
    grpc::Status GetPrice(grpc::ServerContext* ctx, const trading::GetPriceRequest* request, trading::GetPriceResponse* response) override;
    grpc::Status GetAllPrices(grpc::ServerContext* ctx, const trading::GetAllPricesRequest* request, trading::GetAllPricesResponse* response) override;
    grpc::Status HasUser(grpc::ServerContext* ctx, const trading::HasUserRequest* request, trading::HasUserResponse* response) override;


private:
    PriceStore* price_store;
    UserStateStore* user_store;
    WALWriter* wal_writer;
};
