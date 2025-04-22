import os

print("Current Directory:", os.getcwd())

with open("cromo_core/script_build/tmp/hello_world.txt", "w") as file:
    file.write("hello world!\n")
