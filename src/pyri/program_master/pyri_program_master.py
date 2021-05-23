import RobotRaconteur as RR
import threading
from pyri.device_manager_client import DeviceManagerClient
from RobotRaconteurCompanion.Util.DateTimeUtil import DateTimeUtil
from RobotRaconteurCompanion.Util.UuidUtil import UuidUtil
import numpy as np
import uuid
import traceback

class PyriProgramMaster:
    
    def __init__(self, device_manager, device_info = None, node : RR.RobotRaconteurNode = None):
        self._lock = threading.RLock()
        if node is None:
            self._node = RR.RobotRaconteurNode.s
        else:
            self._node = node
        self.device_info = device_info

        self._program_state = self._node.GetStructureType('tech.pyri.program_master.PyriProgramState')
        
        self._device_manager = device_manager
        self._device_manager.connect_device_type("tech.pyri.sandbox.PyriSandbox")
        self._device_manager.connect_device_type("tech.pyri.variable_storage.VariableStorage")
        self._device_manager.refresh_devices(5)
        
        self._refresh_counter = 0

        self._devices = dict()
        self._seqno = 0

        self._date_time_util = DateTimeUtil(self._node)
        self._uuid_util = UuidUtil(self._node)
        self._date_time_utc_type = self._node.GetPodDType('com.robotraconteur.datetime.DateTimeUTC')
        self._isoch_info = self._node.GetStructureType('com.robotraconteur.device.isoch.IsochInfo')
        self._consts = self._node.GetConstants('tech.pyri.program_master')
        self._flags = self._consts["PyriProgramStateFlags"]

        self._current_program = "main"
        self._current_step_id = self._zero_uuid()
        self._current_step_name = ""

        self._running = False
        self._stopped = True
        self._paused = False
        self._stepping = False
        self._error = False
        self._pause_requested = False

        self._procedure_gen = None
        self._procedure_result = None

        try:
            self._read_program()
        except:
            traceback.print_exc()

        try:
            self._load_current_step()
        except:
            traceback.print_exc()

        self._timer = self._node.CreateTimer(0.1, self._timer_cb)
        self._timer.Start()

    def _zero_uuid(self):
        return self._uuid_util.UuidFromPyUuid(uuid.UUID(bytes=b'\x00'*16))

    def RRServiceObjectInit(self, ctx, service_path):
        self._downsampler = RR.BroadcastDownsampler(ctx)
        self._downsampler.AddWireBroadcaster(self.program_state)
        self._downsampler.AddWireBroadcaster(self.device_clock_now)

    def _timer_cb(self,evt):
        with self._lock:
            self._seqno+=1

            s = self._program_state()

            s.ts = self._date_time_util.TimeSpec3Now()
            s.seqno = self._seqno
            
            if len(self._current_program) == 0:
                s.active_program = ""
                s.program_state_flags = self._flags["no_program_loaded"] | self._flags["error"]
            else:
                s.active_program = self._current_program
                flags = 0
                if self._running:
                    flags |= self._flags["running"]
                if self._stopped:
                    flags |= self._flags["stopped"]
                if self._paused:
                    flags |= self._flags["paused"]
                if self._stepping:
                    flags |= self._flags["stepping"]
                if self._error:
                    flags |= self._flags["error"]
                else:
                    flags |= self._flags["ready"]
                s.program_state_flags = flags

                
            s.current_step = self._current_step_id
            s.current_step_name = self._current_step_name

            self.program_state.OutValue = s

    def _read_program(self):
        var_storage = self._device_manager.get_device_client("variable_storage",1)
        program = var_storage.getf_variable_value("program", self._current_program)
        assert program.datatype == "tech.pyri.program_master.PyriProgram", "Requested variable is not a program!"
        return program.data

    def _load_current_step(self):
        var_storage = self._device_manager.get_device_client("variable_storage",1)
        try:
            current_position_rr = var_storage.getf_variable_value("program", "program_master_current_step")
            self._current_step_id = self._uuid_util.UuidFromPyUuid(uuid.UUID(str(current_position_rr.data)))
        except:
            self._current_step_id = self._zero_uuid()
            try:
                var_storage.delete_variable("program", "program_master_current_step")
            except:
                pass
            return

    def _save_current_step(self):
        var_storage = self._device_manager.get_device_client("variable_storage",1)
        if self._current_step_id == self._zero_uuid():
            try:
                var_storage.delete_variable("program", "program_master_current_step")
            except:
                pass
            return

        var_consts = self._node.GetConstants('tech.pyri.variable_storage', var_storage)
        variable_persistence = var_consts["VariablePersistence"]
        variable_protection_level = var_consts["VariableProtectionLevel"]

        step_str = self._uuid_util.UuidToString(self._current_step_id)
        try:
            var_storage.delete_variable("program", "program_master_current_step")
        except:
            traceback.print_exc()
            pass
        var_storage.add_variable2("program","program_master_current_step","string", \
            RR.VarValue(step_str,"string"), ["program_current_step"], {}, variable_persistence["temporary"], None, variable_protection_level["read_write"], \
                [], "program state machine current step uuid", True)

    def _clear_current_step(self):
        var_storage = self._device_manager.get_device_client("variable_storage",1)        
        self._current_step_id = self._zero_uuid()
        try:
            var_storage.delete_variable("program", "program_master_current_step")
        except:
            pass
        return

    def _find_current_step_ind(self, program):
        if self._current_step_id == self._zero_uuid():
            return 0
        u = self._uuid_util.UuidToPyUuid(self._current_step_id)
        for i in range(len(program.steps)):
            if u == self._uuid_util.UuidToPyUuid(program.steps[i].step_id):
                return i
        
        try:
            self._clear_current_step()
        except Exception:
            traceback.print_exc()

        raise RR.InvalidOperationException("Invalid step requested")

    def _move_next_step_next(self, step, program):
        current_ind = -1
        u = self._uuid_util.UuidToPyUuid(step.step_id)                
        for i in range(len(program.steps)):
            if u == self._uuid_util.UuidToPyUuid(program.steps[i].step_id):
                current_ind = i
                break
        if current_ind == -1:
            self._error = True
            self._running = False
            self._paused = False
            self._stepping = False
            self._stopped = True
            self._pause_requested = False
            try:
                self._clear_current_step()
            except:
                pass
            return None

        if not current_ind + 1 < len(program.steps):
            self._error = False
            self._running = False
            self._paused = False
            self._stepping = False
            self._stopped = True
            self._pause_requested = False
            try:
                self._clear_current_step()
            except:
                pass
            return None

        step2 = program.steps[current_ind+1]
        self._current_step_id = step2.step_id
        self._save_current_step()
        return step2

    def _move_next_step_jump(self, step, program, next_id):
        next_ind = -1
        u = self._uuid_util.UuidToPyUuid(next_id)                
        for i in range(len(program.steps)):
            if u == self._uuid_util.UuidToPyUuid(program.steps[i].step_id):
                next_ind = i
                break
        if next_ind == -1:
            self._error = True
            self._running = False
            self._paused = False
            self._stepping = False
            self._stopped = True
            self._pause_requested = False
            try:
                self._clear_current_step()
            except:
                pass
            return None

        step2 = program.steps[next_ind]
        self._current_step_id = step2.step_id
        self._save_current_step()
        return step2

    def _move_next_step(self, step, res):

        program = self._read_program()

        if res is None:
            res = "DEFAULT"
        all_nxt = dict()        
        for nxt1 in step.next:
            all_nxt[nxt1.result.lower()] = nxt1
        
        nxt = all_nxt.get(res.lower(),None)
        if nxt is None:
            if res.lower() == "error":
                self._error = True
                self._running = False
                self._paused = False
                self._stepping = False
                self._stopped = True
                self._pause_requested = False
                return None
            else:
                nxt = all_nxt.get("default",None)
                if nxt is None:
                    return self._move_next_step_next(step,program)

        if nxt.op_code == self._consts["PyriProgramStepNextOpCode"]["stop"]:
            self._error = False
            self._running = False
            self._paused = False
            self._stepping = False
            self._stopped = True
            self._pause_requested = False
            return None

        if nxt.op_code == self._consts["PyriProgramStepNextOpCode"]["error"]:
            self._error = True
            self._running = False
            self._paused = False
            self._stepping = False
            self._stopped = True
            self._pause_requested = False
            return None

        if nxt.op_code == self._consts["PyriProgramStepNextOpCode"]["next"]:            
            return self._move_next_step_next(step,program)

        if nxt.op_code == self._consts["PyriProgramStepNextOpCode"]["jump"]:            
            return self._move_next_step_jump(step,program,nxt.jump_target)

        assert False, "Invalid step opcode"

        

    def _move_and_run_next_step(self, step, res):
        step2 = self._move_next_step(step, res)
        if step2 is not None:
            self._node.PostToThreadPool(lambda: self._run_step(step2))

    def _run_step(self, step):
        try:
            def handler(res,err):
                with self._lock:                    

                    if self._procedure_gen is None:
                        return

                    if self._stopped:
                        gen = self._procedure_gen
                        self._procedure_gen = None
                        self._running = False
                        self._stepping = False
                        self._paused = False
                        if err is None:
                            try:
                                gen.AsyncAbort(lambda e: None)
                            except:
                                pass                        
                        return

                    if err and not isinstance(err,RR.StopIterationException):
                        self._error = True
                        self._running = False
                        self._paused = False
                        self._stepping = False
                        self._stopped = True
                        self._pause_requested = False
                        self._procedure_gen = None                        
                        self._move_and_run_next_step(step, "ERROR")
                        return

                    if res is not None:
                        self._procedure_result = res.result_code
                        self._procedure_gen.AsyncNext(None, handler)
                        return

                    if self._stepping:
                        self._running = False
                        self._paused = True
                        self._stepping = False
                        self._stopped = False
                        self._pause_requested = False
                        self._procedure_gen = None
                        self._move_next_step(step, self._procedure_result)
                        return
                                        
                    if self._pause_requested:
                        self._running = False                        
                        self._stepping = False                        
                        self._pause_requested = False
                        self._procedure_gen = None
                        if not self._stopped:
                            self._paused = True
                        else:
                            self._paused = False
                            return
                        self._move_next_step(step, self._procedure_result)
                        return

                    if self._running:
                        self._move_and_run_next_step(step, self._procedure_result)
                        return                    

            sandbox = self._device_manager.get_device_client("sandbox",1)

            gen = sandbox.execute_procedure(step.procedure_name,step.procedure_args)
            gen.AsyncNext(None,handler)
            self._procedure_result = None
            self._procedure_gen = gen
        except:

            self._error = True
            self._running = False
            self._paused = False
            self._stepping = False
            self._stopped = True
            self._pause_requested = False

            traceback.print_exc()

            raise


    def load_program(self, program_name):
        raise NotImplemented()

    def clear_step_pointer(self):
        with self._lock:
            if self._running or self._stepping:
                raise RR.InvalidOperationException("Cannot clear step pointer while running or stepping")
            if self._error:
                raise RR.InvalidOperationException("Errors must be cleared before clearing step pointer")
            self._clear_current_step()
            self._stopped = True
            self._paused = False
            self._pause_requested = False
            self._error = False

    def setf_step_pointer(self, step_uuid):
        with self._lock:
            if self._running or self._stepping:
                raise RR.InvalidOperationException("Cannot move step pointer while running or stepping")

            if self._error:
                raise RR.InvalidOperationException("Errors must be cleared before moving step pointer")
            program = self._read_program()
            u = self._uuid_util.UuidToPyUuid(step_uuid)
            found = False
            for i in range(len(program.steps)):
                if u == self._uuid_util.UuidToPyUuid(program.steps[i].step_id):
                    found = True

            if not found:
                raise RR.InvalidArgumentException("Invalid step uuid")
            
            self._current_step_id = step_uuid
            self._save_current_step()
            self._stopped = False
            self._paused = True
            self._pause_requested = False
            self._error = False

    def setf_step_pointer_by_name(self, step_name):
        with self._lock:
            if self._running or self._stepping:
                raise RR.InvalidOperationException("Cannot move step pointer while running or stepping")

            if self._error:
                raise RR.InvalidOperationException("Errors must be cleared before moving step pointer")
            program = self._read_program()
            u = None            
            for i in range(len(program.steps)):
                if step_name == program.steps[i].step_name:
                    u = program.steps[i].step_id

            if u is None:
                raise RR.InvalidArgumentException("Invalid step name")
            
            self._current_step_id = u
            self._save_current_step()

    def run(self):
        with self._lock:
            if self._running or self._stepping:
                raise RR.InvalidOperationException("Already running")

            if self._error:
                raise RR.InvalidOperationException("Errors must be cleared before running")
            
            program = self._read_program()

            step_ind = self._find_current_step_ind(program)
            step = program.steps[step_ind]
            self._running = True
            self._paused = False
            self._stepping = False
            self._stopped = False
            self._pause_requested = False

            self._run_step(step)

    def stop(self):
        with self._lock:
            if self._stopped or self._error:
                return
            self._running = True
            self._paused = False
            self._stepping = False
            self._stopped = True
            self._pause_requested = False

            if self._procedure_gen:
                try:
                    self._procedure_gen.AsyncAbort(lambda e: None)
                except:
                    traceback.print_exc()

    def pause(self):
        with self._lock:
            if self._stopped or self._error:
                return
            if self._procedure_gen is None:
                self._paused = True
                self._paused_requested = False
            else:
                self._pause_requested = True

    def step_one(self):
        with self._lock:
            if self._running or self._stepping:
                raise RR.InvalidOperationException("Already running")

            if self._error:
                raise RR.InvalidOperationException("Errors must be cleared before stepping")
            
            program = self._read_program()

            step_ind = self._find_current_step_ind(program)
            step = program.steps[step_ind]
            self._running = False
            self._paused = False
            self._stepping = True
            self._stopped = False
            self._pause_requested = False

            self._run_step(step)

    def clear_errors(self):
        with self._lock:
            if not (self._stopped or self._paused):
                raise RR.InvalidOperationException("Program must be stopped to clear errors")
            self._error = False

    def close(self):
        pass

    @property
    def isoch_downsample(self):
        return self._downsampler.GetClientDownsample(RR.ServerEndpoint.GetCurrentEndpoint())

    @isoch_downsample.setter
    def isoch_downsample(self, value):
        return self._downsampler.SetClientDownsample(RR.ServerEndpoint.GetCurrentEndpoint(),value)

    @property
    def isoch_info(self):
        ret = self._isoch_info()
        ret.update_rate = self._fps
        ret.max_downsample = 100
        ret.isoch_epoch = np.zeros((1,),dtype=self._date_time_utc_type)