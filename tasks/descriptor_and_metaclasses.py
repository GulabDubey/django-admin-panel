# A descriptor in python is an object that controls how an attribute accessed, modified and deleted.

class Name:

    def __get__(self, instance, owner):
        print("Getting name...")
        return instance.__dict__.get("_name")

    def __set__(self, instance, value):
        print("Setting name...")
        instance.__dict__["_name"] = value

    def __delete__(self, instance):
        print("Deleting name...")
        del instance.__dict__["_name"]

class User:
    name = Name()

u = User()
u.name = "Demo"
print(u.name)
del u.name
print(u.name)



# A metaclass is class whose instances are classes

print(type(User))