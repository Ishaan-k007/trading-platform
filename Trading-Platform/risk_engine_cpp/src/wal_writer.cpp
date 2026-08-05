
#include "wal_writer.hpp"
#include <chrono>
#include <sstream>

// std::ios::binary matters here: without it, Windows' text-mode CRT
// silently translates the '\n' below into "\r\n" on write. wal_producer.py
// reads this file expecting plain '\n'-delimited JSON lines - the mismatch
// (compounded by a stale wal.cursor byte offset from an earlier run) caused
// it to seek into the middle of a line and crash on the resulting garbage.
WALWriter::WALWriter(const std::string& path) : file(path, std::ios::app | std::ios::binary) {}


void WALWriter::write_fill(int user_id, const std::string& order_id, const std::string& symbol,
                const std::string& side, const std::string& order_type,
                double quantity, double fill_price,
                double new_cash, double new_quantity, double new_avg_price)

{
   auto time_stamp = std::chrono::system_clock::now().time_since_epoch().count();
   std::ostringstream ss;
    ss << "{\"type\":\"FILL\""
   << ",\"user_id\":"       << user_id
   << ",\"order_id\":\""    << order_id   << "\""
   << ",\"symbol\":\""      << symbol     << "\""
   << ",\"side\":\""        << side       << "\""
   << ",\"order_type\":\""  << order_type << "\""
   << ",\"quantity\":"      << quantity
   << ",\"fill_price\":"    << fill_price
   << ",\"new_cash\":"      << new_cash
   << ",\"new_quantity\":"  << new_quantity
   << ",\"new_avg_price\":" << new_avg_price
   << ",\"timestamp\":"     << time_stamp
   << "}\n";


    std::lock_guard<std::mutex> guard(lock);
    file << ss.str();
    file.flush();


    }