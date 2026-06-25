#pragma once

#include <string>
#include <unordered_map>
#include <shared_mutex>
#include <optional>


struct PriceData {
    double price;
    double volatility;
    double drift;
    std::string updated_at;
};

class PriceStore {
public:
    void set(const std::string& symbol, double price, const std::string& updated_at);
    void init(const std::string& symbol, double price, double volatility, double drift, const std::string& updated_at);
    std::optional<PriceData> get(const std::string& symbol) const;
    std::unordered_map<std::string, double> get_all() const;

private:
    mutable std::shared_mutex mutex_;
    std::unordered_map<std::string, PriceData> prices_;
};
