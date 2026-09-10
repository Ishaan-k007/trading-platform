#include "price_store.hpp"

void PriceStore::add_symbol(const std::string& symbol, double price, double volatility, double drift, const std::string& updated_at) {
    std::unique_lock lock{shared_mutex};
    prices[symbol] = PriceData {price, volatility, drift, updated_at};

}

void PriceStore::set_price(const std::string& symbol, double price, const std::string& updated_at) {
    std::unique_lock lock{shared_mutex};

    auto key = prices.find(symbol);
    if (key != prices.end()) {
        PriceData& data = key->second;
        data.price = price;
        data.updated_at = updated_at;
    }
}


std::optional<PriceData> PriceStore::get_symbol_data(const std::string& symbol) const {
    std::shared_lock lock{shared_mutex};
    
    auto key = prices.find(symbol);
    if (key != prices.end()) {
        return key->second;
    }

    else {
        return std::nullopt;
    }


}


std::unordered_map<std::string, double> PriceStore::get_all() const {
    std::shared_lock lock{shared_mutex};
    std::unordered_map<std::string, double> result;

    for (const auto& [symbol,data] : prices) {
        result[symbol] = data.price;
    }

    return result;


}
