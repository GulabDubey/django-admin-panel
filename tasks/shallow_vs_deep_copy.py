# shallo copy copies only the first layer of object while deep copy also copy the nested objects variables data.
# for example:
import copy

a = {
    "name": "Gulab",
    "skills": {
        "frontend":  ["react", "angular"],
        "backend":  ["php", "node", "python"]
    }
}

# b = a.copy()
b = copy.deepcopy(a)

b["skills"]["frontend"] = ["nextjs", "html/css/js"]

print(f"A : {a}")

print(f"B : {b}") 