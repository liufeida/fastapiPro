abs = lambda x: x if x > 0 else -x

print(abs(-5))

list1 = [1, 2, 3, -4, -5]
print(list(map(lambda x: x if x > 0 else -x, list1)))
print(list(filter(lambda x: x > 0, list1)))
