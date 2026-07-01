const std = @import("std");
const Io = std.Io;

fn add(a: i64, b: i64) i64 {
    return a + b;
}

pub fn main(init: std.process.Init) !void {
    var i: i64 = 0;
    var total: i64 = 0;
    const n: i64 = 200_000;

    while (i < n) : (i += 1) {
        total = add(total, i);
    }

    var stdout_buffer: [64]u8 = undefined;
    var stdout_writer = Io.File.stdout().writer(init.io, &stdout_buffer);
    const stdout = &stdout_writer.interface;
    try stdout.print("{}\n", .{total});
    try stdout.flush();
}
