/* The game and AI-helper runtime: one translation unit of numbered fragments.
 *
 * Included by mellowrt_std.inc after the shared value helpers so std.game and
 * the steering/perception helpers compile into the standalone binary. Every
 * fragment stays under the 300-line ceiling; the dispatcher lives in the last
 * one and is called from the standard-library router. */

#ifndef MELLOWRT_GAME_INC
#define MELLOWRT_GAME_INC

#include "mellowrt_game_part1.inc"
#include "mellowrt_game_part2.inc"
#include "mellowrt_game_part3.inc"
#include "mellowrt_game_part4.inc"
#include "mellowrt_game_part5.inc"
#include "mellowrt_game_part6.inc"

#endif /* MELLOWRT_GAME_INC */
