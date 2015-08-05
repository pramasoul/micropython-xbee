#https://docs.python.org/3.4/library/asyncio-task.html#example-chain-coroutines
import asyncio

@asyncio.coroutine
def compute(x, y):
    print("Compute %s + %s ..." % (x, y))
    yield from asyncio.sleep(0.5)
    return x + y

@asyncio.coroutine
def print_sum(x, y):
    result = yield from compute(x, y)
    print("%s + %s = %s" % (x, y, result))
    return result

work = asyncio.Task(print_sum(1, 2))

@asyncio.coroutine
def watcher():
    print("watching...")
    v = yield from asyncio.wait_for(work, 2.0)
    print("...done, got %s" % v)

watch = asyncio.Task(watcher())

tasks = [ work, watch ]

loop = asyncio.get_event_loop()
loop.run_until_complete(asyncio.wait(tasks))
loop.close()
