#pragma once
#include <unordered_map>
#include <string>
#include <shared_mutex>
#include <optional>
#include <mutex>
#include <vector>
#include <memory>

struct PositionState {

    double quantity;
    double average_price;

};

struct UserState {
    double cash;
    std::unique_ptr<std::mutex> lock;
    std::unordered_map<std::string, PositionState> positions;

};

class UserStateStore {
    public:
        void load_user(int user_id, double cash, const std::vector<std::pair<std::string, PositionState>>& positions);
        bool has_user(int user_id);


        bool check_and_reserve_position(int user_id, const std::string& side, const std::string& symbol, double quantity, double price);

        void update_position(int user_id, const std::string& symbol, double new_cash, double new_quantity, double new_average_price);


    private:
        std::unordered_map<int, UserState> user_positions;
        std::shared_mutex user_positions_mutex;

    };