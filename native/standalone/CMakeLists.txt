cmake_minimum_required(VERSION 3.16)
project(mellowrt C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

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
  src/mellowrt_platform.c
  src/mellowc.c
)
target_include_directories(mellowrt_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
# MSVC exposes math through its C runtime and has no separate libm.
if(NOT MSVC)
  target_link_libraries(mellowrt_core PUBLIC m)
endif()

add_executable(mellowrt src/mellowrt_main.c)
target_link_libraries(mellowrt PRIVATE mellowrt_core)
target_include_directories(mellowrt PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)

add_executable(mellow src/mellowrt_main.c)
target_link_libraries(mellow PRIVATE mellowrt_core)
target_include_directories(mellow PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)

include(CTest)
if(BUILD_TESTING)
  add_test(NAME mellow_runtime_info COMMAND mellow --runtime-info)
  add_test(NAME mellow_version COMMAND mellow --version)
endif()
