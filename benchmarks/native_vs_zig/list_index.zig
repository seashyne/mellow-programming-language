const std = @import("std");
const Io = std.Io;

pub fn main(init: std.process.Init) !void {
    const values = [_]i64{ 1, 2, 3, 4, 5 };
    var i: i64 = 0;
    var total: i64 = 0;
    const n: i64 = 500_000;

    while (i < n) : (i += 1) {
        total += values[@intCast(@mod(i, 5))];
    }

    var stdout_buffer: [64]u8 = undefined;
    var stdout_writer = Io.File.stdout().writer(init.io, &stdout_buffer);
    const stdout = &stdout_writer.interface;
    try stdout.print("{}\n", .{total});
    try stdout.flush();
}
