#pragma once
#include <cstdint>
#include <fstream>
#include <mutex>
#include <string>

// client_order_id = which request is this? Same across retries of the same order purpose: prevents the same client request being executed twice.

// event_id = which fill happened? Unique ID for the committed fill purpose: prevents duplicate fills being processed downstream.

// account_sequence = where does this fill sit in the user’s history? 1, 2, 3... per account — purpose: detects missing or out-of-order fills.
class WALWriter {
public:
    explicit WALWriter(const std::string& path);
    void write_fill(int user_id, const std::string& order_id, const std::string& symbol,
                const std::string& side, const std::string& order_type,
                double quantity, double fill_price,
                double new_cash, double new_quantity, double new_avg_price,
                const std::string& client_order_id, const std::string& event_id, uint64_t account_sequence);
private:
    std::ofstream file;
    std::mutex lock;
};
