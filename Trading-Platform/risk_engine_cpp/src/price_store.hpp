#pragma once

#include <string>
#include <unordered_map>
#include <shared_mutex>
#include <optional>
#include <mutex>


struct PriceData {
    double price;
    double volatility;
    double drift;
    std::string updated_at;
};

class PriceStore {
public:
    void set_price(const std::string& symbol, double price, const std::string& updated_at);
    void add_symbol(const std::string& symbol, double price, double volatility, double drift, const std::string& updated_at);
    std::optional<PriceData> get_symbol_data(const std::string& symbol) const;
    std::unordered_map<std::string, double> get_all() const;

private:
    mutable std::shared_mutex shared_mutex;
    std::unordered_map<std::string, PriceData> prices;
};
