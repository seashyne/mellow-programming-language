local i = 0
local total = 0
local n = 500000

while i < n do
    if i % 2 == 0 then
        total = total + 3
    else
        total = total + 1
    end
    i = i + 1
end

print(string.format("%.0f", total))
