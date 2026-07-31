ls  = ["Gulab", "Sumit", "Gagan"]

itr = iter(ls)

# i = next(itr)
# print(f"i: {i}")
# j = next(itr)
# print(f"j: {j}")
# k = next(itr)
# print(f"k: {k}")


def generator():
    yield "Start..."
    for i in range(1,6):
        yield i
    yield "End..."

for gen in generator():
    print(gen)

def infinite():

    num = 1

    while True:
        yield num
        num += 1

g = infinite()

print(next(g))
print(next(g))
print(next(g))