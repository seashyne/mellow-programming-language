i = 0
total = 0
n = 500_000

while i < n:
    if i % 2 == 0:
        total += 3
    else:
        total += 1
    i += 1

print(total)
