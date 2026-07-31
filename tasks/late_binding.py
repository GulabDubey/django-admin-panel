# Late binding-> uses of variable inside of a closure
# -looked up when the function is called
# -not when the function is created

functions = []

for i in range(1,6):
    functions.append(lambda: i)

for fn in functions:
    print(fn())

print('Fixed using default arguments:')

for i in range(1,6):
    functions.append(lambda i=i: i)

for fn in functions:
    print(fn())