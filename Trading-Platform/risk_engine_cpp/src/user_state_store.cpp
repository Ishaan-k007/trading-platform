#include "user_state_store.hpp"


void UserStateStore::load_user(int user_id, double cash, const std::vector<std::pair<std::string, PositionState>>& positions) {
    std::unique_lock lock{user_positions_mutex};

    UserState state;
    state.cash = cash;
    state.lock =  std::make_unique<std::mutex>();

    for (const auto& [symbol,pos] : positions) {
        state.positions[symbol] = pos;

    }

    user_positions[user_id] = std::move(state);
}

 bool UserStateStore::has_user(int user_id) {
    std::shared_lock lock{user_positions_mutex};
    if (user_positions.find(user_id) != user_positions.end()) {
        return true;
    }

    else {
        return false;
    }


 }

bool UserStateStore::check_and_reserve_position(int user_id, const std::string& side, const std::string& symbol, double quantity, double price){
    std::shared_lock lock{user_positions_mutex};

    if (user_positions.find(user_id) == user_positions.end()) {
        return false;
    }
    
    UserState& user = user_positions[user_id];
    std::unique_lock lock2{*user.lock};
    
    lock.unlock();

    if (side == "BUY") {
        if (user.cash >= quantity * price) {
            user.cash = user.cash - quantity * price;
            return true;
        }
        else {
            return false;
        }
    }

    if (side == "SELL") {
        if (user.positions[symbol].quantity >= quantity) {
            user.positions[symbol].quantity = user.positions[symbol].quantity - quantity;
            return true;
        }
        else {
            return false;
        }
    }
    return false;
}


void UserStateStore::update_position(int user_id, const std::string& symbol, double new_cash, double new_quantity, double new_average_price) {
    std::shared_lock lock{user_positions_mutex};
    if (user_positions.find(user_id) == user_positions.end()) {
        return;
    }

    UserState& user = user_positions[user_id];
    std::unique_lock lock2{*user.lock};
    user.cash = new_cash;
    user.positions[symbol].quantity = new_quantity;
    user.positions[symbol].average_price = new_average_price;

}


