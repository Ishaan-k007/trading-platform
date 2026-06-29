cmake_minimum_required(VERSION 3.20)
project(risk_engine CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(Protobuf CONFIG REQUIRED)
find_package(gRPC CONFIG REQUIRED)
set(PROTO_FILE "${CMAKE_SOURCE_DIR}/proto/trading.proto")
set(PROTO_OUT  "${CMAKE_BINARY_DIR}")

set(PROTO_SRCS "${PROTO_OUT}/trading.pb.cc")
set(PROTO_HDRS "${PROTO_OUT}/trading.pb.h")
set(GRPC_SRCS  "${PROTO_OUT}/trading.grpc.pb.cc")
set(GRPC_HDRS  "${PROTO_OUT}/trading.grpc.pb.h")

add_custom_command(
    OUTPUT "${PROTO_SRCS}" "${PROTO_HDRS}" "${GRPC_SRCS}" "${GRPC_HDRS}"
    COMMAND $<TARGET_FILE:protobuf::protoc>
        --cpp_out="${PROTO_OUT}"
        --grpc_out="${PROTO_OUT}"
        --plugin=protoc-gen-grpc="$<TARGET_FILE:gRPC::grpc_cpp_plugin>"
        -I "${CMAKE_SOURCE_DIR}/proto"
        "${PROTO_FILE}"
    DEPENDS "${PROTO_FILE}"
    COMMENT "Generating protobuf and gRPC C++ files"
)

set(SOURCES
    src/main.cpp
    src/price_store.cpp
    src/user_state_store.cpp
    src/trading_service.cpp
    ${PROTO_SRCS}
    ${GRPC_SRCS}
)
add_executable(risk_engine ${SOURCES})
target_include_directories(risk_engine PRIVATE
    "${PROTO_OUT}"
    "${CMAKE_SOURCE_DIR}/src"
    ${Protobuf_INCLUDE_DIRS}
)

target_link_libraries(risk_engine PRIVATE
    gRPC::grpc++
    gRPC::grpc++_reflection
    protobuf::libprotobuf
    pq
)