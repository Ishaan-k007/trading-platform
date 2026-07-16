#include <iostream>
#include <thread>
#include <chrono>
#include <cmath>
#include <random>
#include <string>
#include <libpq-fe.h>
#include <grpcpp/grpcpp.h>
#include "price_store.hpp"
#include "user_state_store.hpp"
#include "trading_service.hpp"
#include <ctime>
#include "wal_writer.hpp"
#include "order_book.hpp"




void run_gbm(PriceStore* store) {
    // Implementation for running GBM simulation
    std::mt19937 gen(std::random_device{}());
    std::normal_distribution<double> dist(0.0, 1.0);
    while (true) {
    std::this_thread::sleep_for(std::chrono::seconds(1));
        auto snapshot = store->get_all();

        for (const auto& [symbol, _] : snapshot) {
            auto data = store->get_symbol_data(symbol);
            if (!data.has_value()) continue;

            double Z = dist(gen);
            double new_price = data->price * std::exp((data->drift - 0.5 * data->volatility * data->volatility) * 1.0 + data->volatility * std::sqrt(1.0) * Z);
            auto now = std::chrono::system_clock::now();
            std::time_t t = std::chrono::system_clock::to_time_t(now);
            std::string ts = std::string(std::ctime(&t));
            ts.pop_back();

            store->set_price(symbol, new_price, ts);
        }
    }


}

int main(){
    PGconn* connection = PQconnectdb("host=localhost port=5433 dbname=trading_platform user=trading_user password=trading_pass");
    if (PQstatus(connection) != CONNECTION_OK) {
        std::cerr << "DB connection failed: " << PQerrorMessage(connection) << "\n";
        PQfinish(connection);
        return 1; // exit with failure code
        }
    std::cout << "Connected to PostgreSQL\n";

    PriceStore price_store;
    UserStateStore user_store;
    OrderBook order_book;

    PGresult* res = PQexec(connection, "SELECT symbol, price, volatility, drift FROM market_prices");
    if (PQresultStatus(res) != PGRES_TUPLES_OK) {
    std::cerr << "Query failed: " << PQerrorMessage(connection) << "\n";
    PQclear(res);
    PQfinish(connection);
    return 1;
    }

    int rows = PQntuples(res);
    for (int i = 0; i < rows; i++) {
        std::string symbol = PQgetvalue(res, i, 0);
        double price = std::stod(PQgetvalue(res, i, 1));
        double volatility = std::stod(PQgetvalue(res, i, 2));
        double drift = std::stod(PQgetvalue(res, i, 3));
        price_store.add_symbol(symbol, price, volatility, drift, "startup");
    }
    PQclear(res);
    PQfinish(connection);
    std::cout << "Loaded " << rows << " symbols into PriceStore\n";
    
    WALWriter wal_writer("wal.log");
   
    // GBM simulation disconnected for now - real Binance order book data drives pricing instead.
    // Uncomment to re-enable GBM-simulated pricing for symbols not covered by live order book data.
    // std::thread gbm_thread(run_gbm, &price_store);
    // gbm_thread.detach();
    TradingServiceImplementation service(&price_store, &user_store, &wal_writer, &order_book);
    grpc::ServerBuilder builder;
    builder.AddListeningPort("0.0.0.0:50051", grpc::InsecureServerCredentials());
    builder.RegisterService(&service);
    std::unique_ptr<grpc::Server> server = builder.BuildAndStart();
    std::cout << "gRPC server listening on port 50051\n";
    server->Wait();












}