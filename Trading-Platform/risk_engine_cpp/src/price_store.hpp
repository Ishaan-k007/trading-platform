#pragma once

#include <string>
#include <unordered_map>
#include <shared_mutex>
#include <optional>
#include <mutex>

/* Holds simulation data for a stock, once volatility and drift are set up they dont change, however price changes per GBM tick */
struct PriceData {
    double price;
    double volatility;
    double drift;
    std::string updated_at;
};

/**
 * @brief Thread-safe in-memory cache of current stock prices and GBM parameters.
 *
 * Written by the GBM simulation thread once per second via set_price().
 * Read by gRPC server threads on every CheckOrder and GetPrice call.
 * Exists to eliminate PostgreSQL round-trips on the risk check hot path.
 *
 * Uses shared_mutex so that multiple readers run concurrently, writer is exclusive.
 */

class PriceStore {
public:
    

    /**
    * @brief Updates price and timestamp for an existing symbol. Called every second by GBM thread.
    *
    * Intentionally does not update volatility or drift which are constants.
    * No operation if symbol was never seeded via add_symbol.
    *
    * @param symbol     Ticker to update
    * @param price      New price from GBM calculation
    * @param updated_at ISO timestamp of this tick
    */

    void set_price(const std::string& symbol, double price, const std::string& updated_at);


    /**
    * @brief Seeds one symbol into the store from PostgreSQL (market_prices table) on startup.
    *
    * Called once per symbol before the gRPC server and GBM thread start.
    * Sets all fields including volatility and drift, which never change after this.
    *
    * @param symbol      Ticker string e.g. "AAPL"
    * @param price       Current price from market_prices table
    * @param volatility  GBM sigma — controls price jump magnitude
    * @param drift       GBM mu — controls directional trend
    * @param updated_at  ISO timestamp string
    */

    
    void add_symbol(const std::string& symbol, double price, double volatility, double drift, const std::string& updated_at);
    
    
    
    std::optional<PriceData> get_symbol_data(const std::string& symbol) const;
    std::unordered_map<std::string, double> get_all() const;

private:
    mutable std::shared_mutex shared_mutex;
    std::unordered_map<std::string, PriceData> prices;
};
