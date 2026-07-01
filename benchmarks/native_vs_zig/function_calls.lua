local function add(a, b)
    return a + b
end

local i = 0
local total = 0
local n = 200000

while i < n do
    total = add(total, i)
    i = i + 1
end

print(string.format("%.0f", total))
