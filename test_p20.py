#https://docs.python.org/3.4/library/asyncio-task.html#example-parallel-execution-of-tasks
import asyncio

@asyncio.coroutine
def factorial(name, number):
    f = 1
    for i in range(2, number+1):
        #print("Task %s: Compute factorial(%s)..." % (name, i))
        yield from asyncio.sleep(0.01)
        f *= i
    print("Task %s: factorial(%s) = %s" % (name, number, f))

tasks = list(asyncio.Task(factorial(chr(64+n), 2+n)) for n in range(100))

loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.wait(tasks))
loop.close()
