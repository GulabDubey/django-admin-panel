# closures are created when an inner function has access to it's outter functions variable even after the outer function called.
# for example:

def outer():
    x = 10
    def inner(y):
        return x + y
    return inner

add10 = outer()

print(add10(5))
