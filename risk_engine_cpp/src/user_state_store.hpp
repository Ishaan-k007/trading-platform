#pragma once
#include <unordered_map>
#include <string>
#include <shared_mutex>
#include <optional>
#include <mutex>
#include <vector>
#include <memory>
#include <cstdint>
class WALWriter;   // forward declaration : Why class WALWriter; instead of #include "wal_writer.hpp": execute_order takes a WALWriter* a pointer. To hold a pointer, the compiler only needs to know the name WALWriter exists, not its full definition. 

struct PositionState {

    double quantity;
    double average_price;

};



enum class ExecOutcome {
    Filled,
    InsufficientFunds,
    InsufficientPosition,
    InvalidOrder,
    IdempotencyConflict,
};
// Stores everything execute_order() needs to return in one object.
// It exists because executing an order can produce lots of information:
// success/rejection status, updated account values, IDs, sequence number,
// and idempotency data, so returning a single struct is cleaner than many values.
//
// Numeric fields start at 0 by default, then execute_order() overwrites the
// relevant ones after it updates the user's actual account state.
struct ExecuteResult {
    ExecOutcome outcome;
    double fill_price = 0, new_cash = 0, new_quantity = 0, new_average_price = 0;
    double required_cash = 0, available_cash = 0;
    double required_quantity = 0, available_quantity = 0;
    uint64_t account_sequence = 0;
    std::string order_id, event_id;
    bool from_cache = false;
    std::string req_side, req_symbol;   // what was ordered — used to detect id reuse
    double req_quantity = 0;
};

struct UserState {
    double cash;
    std::unique_ptr<std::mutex> lock;
    std::unordered_map<std::string, PositionState> positions;
    uint64_t sequence = 0;
    std::unordered_map<std::string, ExecuteResult> idempotency;

};


class UserStateStore {
    public:
        void load_user(int user_id, double cash, const std::vector<std::pair<std::string, PositionState>>& positions);
        bool has_user(int user_id);
        


        ExecuteResult execute_order(int user_id, const std::string& client_order_id,
                                    const std::string& side, const std::string& symbol,
                                    double quantity, double fill_price,
                                    WALWriter* wal, const std::string& order_type);


        


    private:
        std::unordered_map<int, UserState> user_positions;
        std::shared_mutex user_positions_mutex;

    };