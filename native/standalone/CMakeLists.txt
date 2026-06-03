cmake_minimum_required(VERSION 3.16)
project(mellowrt C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

add_library(mellowrt_core STATIC
  src/mellowrt_core.c
  src/mellowrt_debug.c
)
target_include_directories(mellowrt_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
# v2.3.4: link libm for pow/sqrt/fmod/floor/ceil/fabs
target_link_libraries(mellowrt_core PUBLIC m)

add_executable(mellowrt src/mellowrt_main.c)
target_link_libraries(mellowrt PRIVATE mellowrt_core)
target_include_directories(mellowrt PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)
