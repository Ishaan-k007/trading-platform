#include "order_book.hpp"


void OrderBook::update(const std::string& symbol, const std::vector<PriceLevel>&bids, const std::vector<PriceLevel>& asks, const std::string& updated_at) {
    /* Individual locks for each symbol*/
    std::shared_lock lock{books_mutex};
    auto it = books.find(symbol);
    /* Top level lock for keys*/
    std::unique_lock<std::mutex> entry_lock;
    if (it == books.end()) {
        lock.unlock();
        std::unique_lock exclusive{books_mutex};
        it = books.find(symbol);
        if (it == books.end()) {

            OrderBookEntry entry;
            entry.bids = bids;
            entry.asks = asks;
            entry.updated_at = updated_at;
            entry.lock =  std::make_unique<std::mutex>();
            books[symbol] = std::move(entry);
        }
        it = books.find(symbol);
        entry_lock = std::unique_lock<std::mutex>(*it->second.lock);
        exclusive.unlock();
    }

    else {
        entry_lock = std::unique_lock<std::mutex>(*it->second.lock);
        lock.unlock();
    }

    
    it->second.bids = bids; it->second.asks = asks; it->second.updated_at = updated_at;

};

std::optional<double> OrderBook::best_bid(const std::string& symbol) const {
    std::unique_lock<std::mutex> entry_lock;
    std::shared_lock lock{books_mutex};
    auto it = books.find(symbol);
    
    if (it == books.end()) {
        return std::nullopt;
    }
    entry_lock = std::unique_lock<std::mutex>(*it->second.lock);
    if (it->second.bids.empty()) {
        return std::nullopt;
    }
    return it->second.bids.front().price;
}

std::optional<double> OrderBook::best_ask(const std::string& symbol) const {
    std::unique_lock<std::mutex> entry_lock;
    std::shared_lock lock{books_mutex};
    auto it = books.find(symbol);
    if (it == books.end()) {
        return std::nullopt;
    }
    entry_lock = std::unique_lock<std::mutex>(*it->second.lock);
    if (it->second.asks.empty()) {
        return std::nullopt;
    }
    return it->second.asks.front().price;
}

std::optional<double> OrderBook::spread(const std::string& symbol) const {
    auto bid = best_bid(symbol);
    auto ask = best_ask(symbol);
    if (!bid || !ask) return std::nullopt;
    return *ask - *bid;
}

std::optional<double> OrderBook::imbalance(const std::string& symbol) const {
    std::unique_lock<std::mutex> entry_lock;
    std::shared_lock lock{books_mutex};
    auto it = books.find(symbol);
    if (it == books.end()) {
        return std::nullopt;
    }
    entry_lock = std::unique_lock<std::mutex>(*it->second.lock);

    double bid_total = 0;
    for (const auto& level : it->second.bids) {
        bid_total += level.quantity;
    }

    double ask_total = 0;
    for (const auto& level : it->second.asks) {
        ask_total += level.quantity;
    }

    if (bid_total + ask_total == 0) {
        return std::nullopt;
    }

    return bid_total / (bid_total + ask_total);
}
