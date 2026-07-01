def add(a, b):
    return a + b


i = 0
total = 0
n = 200_000

while i < n:
    total = add(total, i)
    i += 1

print(total)
