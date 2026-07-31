# A context manager is a python feature that automatically sets up and cleans up resources.

# it ensures that resources like: files, database connections, locks and network sockets are properly released
# even if an exception occurs

with open("tasks/closures.py", "r") as file:
    data = file.read()

exec(data)