#pragma once
#include <fstream>
#include <mutex>
#include <string>


class WALWriter {
public:
    explicit WALWriter(const std::string& path);
    void write_fill(int user_id, const std::string& order_id, const std::string& symbol,
                const std::string& side, const std::string& order_type,
                double quantity, double fill_price,
                double new_cash, double new_quantity, double new_avg_price);
private:
    std::ofstream file;
    std::mutex lock;
};
