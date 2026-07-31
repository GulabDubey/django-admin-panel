"""
Python -> high-level, interpreted, dynamically typed language -> known for readability and simplicity
List vs Tuple -> List (Mutable, [] syntax, slower performance) and Tuple (Immutable, () syntax, fast performance)
Dict vs Set -> Dict (ordered collections of key-value pair, mutable, unique by key) and Set (mutable, )
Datatypes: (int, float, bool, str) and (list, tuple, dic, set)
Indentation: Python uses indentation instead of {}. for ex: if True: print("Hello")
Variable: a name that refers to a value
Shallow vs Deep copy: SC creates new objects but reference to its nested objects and DC creates completely new objects without reference to nested objects
*args vs **kwargs: *args (multiple positional arguments, used when don't know no of passed args) and **kwargs (multiple keyword arguments, use when u want to accept names args dynamically)
list comprehension: short way to create list
lamda function: anonymous one-line function for ex: square = lambda x: x*x
== and is: "==" compares the value and "is" compare the memory location. for ex: a=[1,2,3], b=[1,2,3], print(a==b)
    a=[1,2,3]
    b=[1,2,3]
    print(a==b, a is b)
decorators: functions that modifies other functions
"""

# print([x*x for x in range(1,11)])
# print(tuple(x*x for x in range(1,11)))
# print({x*x for x in range(1,11)})
# print({x:x*x for x in range(1,11)})

#regular function
# def add(a,b):
#     return a+b
# print(add(10,20))

#lambda function:
# square = lambda x: x*x
# print(square(10))

# numbers = [1,2,3,4,5]
# mp = map(square, numbers)
# ls = list(mp)
# print(ls)

# print(list(filter(lambda x: x%2==0, [1,2,3,4,5,6,7])))

# from functools import reduce
# print(reduce(lambda x, curr: x*curr, range(1, 6)))

# students = [("Amit", 10), ("Anuj", 5), ("Pankaj", 8)]
# students.sort(key=lambda x: x[1])
# students.reverse()
# print(students)

# closures using lambda
# def incrementer(n):
#     return lambda x: x+n
# inc5 = incrementer(5)
# print(inc5(10))
# print(inc5(20))

# max_num = lambda x, y: x if x > y else y
# print(max_num(2,10))

# ls = [1,2,3,4,5]
# print(ls)
# ls[0] = 10
# print(ls)

# tp = (1,2,3,4,5)
# print(tp)
# # tp[0] = 10
# tp = list(tp)
# tp[0] = 10
# tp = tuple(tp)
# print(tp)

# dic = {"a":1, "b":2, "c":3}
# print(dic)

# st = {1,2,1,2,3} #set((1,2,3,4,5,5,4))
# print(st)

# if True: print("Hello")
# import copy

# arr = [1,2,3,[4,5]]
# newArr = copy.deepcopy(arr) #copy.copy(arr) OR arr[:]
# newArr[0] = 11
# newArr[3][0] = 99
# print(arr, newArr)

# def fun(a, *args, **kwargs): # *args: collect in tuple, **kwargs: collect in dict 
#     print(a, args, kwargs)

# fun(1,2,3,4,5, name="Gulab", age=23)