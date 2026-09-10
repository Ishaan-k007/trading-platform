#include "user_state_store.hpp"

// Why include wal_writer.hpp here when the header only forward-declared it: the forward declaration class WALWriter; was enough to hold a WALWriter*. But in this file we actually call wal->write_fill(...), and to type-check that call the compiler needs the full class — the method's name, its parameter list. That full definition lives in wal_writer.hpp. General rule: forward-declare in headers, #include in the .cpp where you use the type for real.

//Why <random>: it gives us std::mt19937_64, a pseudo-random number generator, which we use to make the order/event IDs.
#include "wal_writer.hpp"
#include <random>

//  builds a 32-character random hex string like a3f90c17... — used for order_id (the server's canonical ID for the order) and event_id (the ID for this one committed fill)
namespace {
std::string random_id() {
    static thread_local std::mt19937_64 gen{std::random_device{}()};
    static const char* hex = "0123456789abcdef";
    std::string s(32, '0');
    for (auto& c : s) c = hex[gen() & 0xF];
    return s;
}
}



void UserStateStore::load_user(int user_id, double cash, const std::vector<std::pair<std::string, PositionState>>& positions) {
    std::unique_lock lock{user_positions_mutex};

    if (user_positions.find(user_id) != user_positions.end()) {
        return;
    }
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


ExecuteResult UserStateStore::execute_order(
        int user_id, const std::string& client_order_id,
        const std::string& side, const std::string& symbol,
        double quantity, double fill_price,
        WALWriter* wal, const std::string& order_type) {

    // Look up the user under a shared (read) lock on the map, then take
    //     THAT user's own lock and hold it for the whole function.
    std::shared_lock map_lock{user_positions_mutex};
    auto it = user_positions.find(user_id);
    if (it == user_positions.end()) {
        return {ExecOutcome::InvalidOrder};
    }
    UserState& user = it->second;
    std::unique_lock user_lock{*user.lock};
    map_lock.unlock();

    // Idempotency: already executed this client_order_id for this user?
    if (auto cached = user.idempotency.find(client_order_id);
            cached != user.idempotency.end()) {
        const ExecuteResult& prev = cached->second;
        if (prev.req_side != side || prev.req_symbol != symbol
                || prev.req_quantity != quantity) {
            return {ExecOutcome::IdempotencyConflict};
        }
        ExecuteResult replay = prev;
        replay.from_cache = true;
        return replay;
    }

    // Validate funds / position and apply the change — still holding the lock.
    ExecuteResult res{};
    res.fill_price = fill_price;
    PositionState& pos = user.positions[symbol];

    if (side == "BUY") {
        double cost = quantity * fill_price;
        if (user.cash < cost) {
            res.outcome = ExecOutcome::InsufficientFunds;
            res.required_cash = cost;
            res.available_cash = user.cash;
            return res;
        }
        double new_qty = pos.quantity + quantity;
        pos.average_price =
            (pos.average_price * pos.quantity + fill_price * quantity) / new_qty;
        pos.quantity = new_qty;
        user.cash -= cost;
    } else if (side == "SELL") {
        if (pos.quantity < quantity) {
            res.outcome = ExecOutcome::InsufficientPosition;
            res.required_quantity = quantity;
            res.available_quantity = pos.quantity;
            return res;
        }
        pos.quantity -= quantity;
        user.cash += quantity * fill_price;
    } else {
        return {ExecOutcome::InvalidOrder};
    }

    // Committed. Assign IDs, bump this user's sequence number.
    user.sequence += 1;
    res.outcome = ExecOutcome::Filled;
    res.order_id = random_id();
    res.event_id = random_id();
    res.new_cash = user.cash;
    res.new_quantity = pos.quantity;
    res.new_average_price = pos.average_price;
    res.account_sequence = user.sequence;
    res.req_side = side;
    res.req_symbol = symbol;
    res.req_quantity = quantity;

    // Write the WAL entry while STILL holding the lock.
    wal->write_fill(user_id, res.order_id, symbol, side, order_type,
                    quantity, fill_price,
                    res.new_cash, res.new_quantity, res.new_average_price,
                    client_order_id, res.event_id, res.account_sequence);

    // Remember this result so a retry replays it instead of re-executing.
    user.idempotency[client_order_id] = res;
    return res;
}

