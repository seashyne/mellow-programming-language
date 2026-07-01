values = [1, 2, 3, 4, 5]
i = 0
total = 0
n = 500_000

while i < n:
    total += values[i % 5]
    i += 1

print(total)
