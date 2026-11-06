cmake_minimum_required(VERSION 3.16)
project(mellowrt C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

option(MELLOW_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
option(MELLOW_BUILD_FUZZER "Build the libFuzzer compiler/runtime target" OFF)

if(MELLOW_ENABLE_SANITIZERS)
  if(MSVC)
    message(FATAL_ERROR "MELLOW_ENABLE_SANITIZERS currently requires Clang or GCC")
  endif()
  add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
  add_link_options(-fsanitize=address,undefined)
endif()

string(TOLOWER "${CMAKE_SYSTEM_PROCESSOR}" MELLOW_SYSTEM_PROCESSOR)
if(MELLOW_SYSTEM_PROCESSOR MATCHES "^(aarch64|arm64)$")
  set(MELLOW_TARGET_ARCH "arm64")
  add_compile_definitions(MELLOW_ARCH_ARM64=1)
elseif(MELLOW_SYSTEM_PROCESSOR MATCHES "^arm")
  set(MELLOW_TARGET_ARCH "arm32")
  add_compile_definitions(MELLOW_ARCH_ARM32=1)
elseif(MELLOW_SYSTEM_PROCESSOR MATCHES "^(x86_64|amd64|x64)$")
  set(MELLOW_TARGET_ARCH "x86_64")
  add_compile_definitions(MELLOW_ARCH_X86_64=1)
else()
  set(MELLOW_TARGET_ARCH "generic")
  add_compile_definitions(MELLOW_ARCH_UNKNOWN=1)
endif()

message(STATUS "Mellow target architecture: ${MELLOW_TARGET_ARCH}")

add_library(mellowrt_core STATIC
  src/mellowrt_core.c
  src/mellowrt_debug.c
  src/mellowrt_ledger.c
  src/mellowrt_money.c
  src/mellowrt_platform.c
  src/mellowrt_packages.c
  src/mellowrt_pkg.c
  src/mellowrt_scheduler.c
  src/mellowrt_server.c
  src/mellowrt_sm_cli.c
  src/mellowrt_storage.c
  src/mellowrt_syscalls.c
  src/mellow_runtime.c
  src/mellowc.c
  src/mellowc_lexer.c
  src/mellowc_modules.c
  src/mellowc_parser.c
  ../sm/src/sm_native.c
  vendor/sqlite/sqlite3.c
)
target_include_directories(mellowrt_core PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/include
  ${CMAKE_CURRENT_SOURCE_DIR}/../sm/include
)
target_include_directories(mellowrt_core PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/vendor/sqlite
)
# MSVC exposes math through its C runtime and has no separate libm.
if(NOT MSVC)
  target_link_libraries(mellowrt_core PUBLIC m)
endif()
if(WIN32)
  target_link_libraries(mellowrt_core PUBLIC ws2_32)
elseif(NOT CMAKE_CROSSCOMPILING)
  # HTTPS for the package client; http:// works without any TLS library.
  find_package(CURL QUIET)
  if(CURL_FOUND)
    target_compile_definitions(mellowrt_core PRIVATE MELLOW_HAVE_LIBCURL=1)
    target_link_libraries(mellowrt_core PUBLIC CURL::libcurl)
  endif()
endif()

add_executable(mellowrt src/mellowrt_main.c)
target_link_libraries(mellowrt PRIVATE mellowrt_core)
target_include_directories(mellowrt PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)

add_executable(mellow src/mellowrt_main.c)
target_link_libraries(mellow PRIVATE mellowrt_core)
target_include_directories(mellow PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)

if(MELLOW_BUILD_FUZZER)
  if(NOT CMAKE_C_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "MELLOW_BUILD_FUZZER requires Clang/libFuzzer")
  endif()
  add_executable(mellow_fuzz fuzz/fuzz_mellow.c)
  target_link_libraries(mellow_fuzz PRIVATE mellowrt_core)
  target_include_directories(mellow_fuzz PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
  target_compile_options(mellow_fuzz PRIVATE -fsanitize=fuzzer)
  target_link_options(mellow_fuzz PRIVATE -fsanitize=fuzzer,address,undefined)
endif()

include(CTest)
if(BUILD_TESTING)
  add_test(NAME mellow_runtime_info COMMAND mellow --runtime-info)
  add_test(NAME mellow_version COMMAND mellow --version)
  add_test(
    NAME mellow_core_conformance
    COMMAND mellow ${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/full_native_core.mellow
  )
  add_test(
    NAME mellow_ledger_conformance
    COMMAND mellow ${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/ledger_core.mellow
  )
  file(MAKE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/storage-core)
  add_test(
    NAME mellow_storage_conformance
    COMMAND mellow ${CMAKE_CURRENT_SOURCE_DIR}/../../tests/fixtures/storage_core.mellow
  )
  set_tests_properties(mellow_storage_conformance PROPERTIES
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/storage-core
  )
endif()
