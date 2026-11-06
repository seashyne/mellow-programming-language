local values = {1, 2, 3, 4, 5}
local i = 0
local total = 0
local n = 500000

while i < n do
    total = total + values[(i % 5) + 1]
    i = i + 1
end

print(string.format("%.0f", total))
