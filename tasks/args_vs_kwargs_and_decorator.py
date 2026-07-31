def my_dec(fn):
    def wrapper(*args):
        result = fn(args[0], args[1]);
        return result
    return wrapper

@my_dec
def fun(a,b):
    return a+b

print(fun(10,5))