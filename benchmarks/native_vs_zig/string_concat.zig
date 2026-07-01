const std = @import("std");
const Io = std.Io;

pub fn main(init: std.process.Init) !void {
    var buffer: [2000]u8 = undefined;
    var i: usize = 0;
    const n: usize = 2000;

    while (i < n) : (i += 1) {
        buffer[i] = 'a';
    }

    var stdout_buffer: [64]u8 = undefined;
    var stdout_writer = Io.File.stdout().writer(init.io, &stdout_buffer);
    const stdout = &stdout_writer.interface;
    try stdout.print("{}\n", .{n});
    try stdout.flush();
}
