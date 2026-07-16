#pragma once
#include <vector>
#include <string>
#include <mutex>
#include <memory>
#include <unordered_map>
#include <shared_mutex>
#include <optional>
struct PriceLevel {
    double price;
    double quantity;
};

struct OrderBookEntry {
    std::vector<PriceLevel> bids;
    std::vector<PriceLevel> asks;
    std::string updated_at;
    std::unique_ptr<std::mutex> lock;
};

class OrderBook {
    private:
        std::unordered_map<std::string, OrderBookEntry> books;
        mutable std::shared_mutex books_mutex;
    public:
        void update(const std::string& symbol, const std::vector<PriceLevel> & bids, const std::vector<PriceLevel>& asks,const std::string& updated_at);
        std::optional<double> best_bid(const std::string& symbol) const;

        std::optional<double> best_ask(const std::string& symbol) const;

        std::optional<double> spread(const std::string& symbol) const;

        std::optional<double> imbalance(const std::string& symbol) const;



};


