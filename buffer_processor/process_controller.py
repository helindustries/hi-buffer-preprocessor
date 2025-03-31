#  Copyright 2025 $author, All rights reserved.
import multiprocessing
import sys

class ProcessController:
    def __init__(self, max_threads: int = float("inf"), set_start_method = True, use_main_process = False):
        if set_start_method:
            self.__class__.set_start_method(self.__class__)
        self.processes: list[multiprocessing.Process] = []
        self.max_threads: int = max_threads
        self.use_main_process = True
        self.main_running = False
        self.manager: multiprocessing.Manager = multiprocessing.Manager()
    def available(self):
        return self.max_threads - len(self.processes) - (1 if self.main_running else 0)
    def running(self):
        return len(self.processes) + (1 if self.main_running else 0)
    def start(self, target, args):
        while self.available() < 1:
            for process in self.processes:
                if not process.is_alive():
                    self.processes.remove(process)
                    break
        if self.available() == 1 and self.use_main_process:
            self.main_running = True
            target(*args)
            self.main_running = False
        else:
            process = multiprocessing.Process(target=target, args=args)
            process.start()
            self.processes.append(process)
    def join_finished(self):
        count = 0
        for process in self.processes:
            if not process.is_alive():
                process.join()
                self.processes.remove(process)
                count += 1
        return count + (1 if self.main_running else 0)
    def join_all(self):
        count = 0
        for process in self.processes:
            process.join()
            self.processes.remove(process)
            count += 1
        return count
    def kill_all(self):
        count = 0
        for process in self.processes:
            process.kill()
            self.processes.remove(process)
            count += 1
        return count
    @staticmethod
    def set_start_method(cls):
        if not hasattr(cls, "start_method_set") or not cls.start_method_set:
            if sys.platform == "win32":
                multiprocessing.set_start_method("spawn")
            else:
                multiprocessing.set_start_method("fork")
            cls.start_method_set = True
