local i = 0
local total = 0
local n = 2000000

while i < n do
    total = total + i
    i = i + 1
end

print(string.format("%.0f", total))
