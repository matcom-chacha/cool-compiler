from atexit import register
from email.quoprimime import body_length
import enum
from operator import le
from tkinter.tix import Select
from attr import attr

from soupsieve import select
import cmp.visitor as visitor
import cmp.cil as cil
import random

import mips_nodes as mips



#type_info offsets
TYPENAME_OFFSET = 0
FUNCTION_OFFSET = 4
RA_OFFSET = 8
OLD_FP_OFFSET = 4

FP_ARGS_DISTANCE = 3 # how far finishes $fp from arguments in method call
FP_LOCALS_DISTANCE = 0 # how far finishes $fp from localvars in method call

ABORT_SIGNAL = "abort_signal"#CIL
CASE_MISSMATCH = "case_missmatch"#CIL
CASE_VOID = "case_on_void"#MIPS
DISPATCH_VOID = "dispatch_on_void"#MIPS
ZERO_DIVISION = "division_by_zero"#MIPS
SUBSTR_OUT_RANGE = "substr_out_of_range"#MIPS
HEAP_OVERFLOW = "heap_overflow"

#temporary registers
t0 = "$t0"
t1 = "$t1"
t2 = "$t2"
t3 = "$t3"
t4 = "$t4"
t5 = "$t5"
t6 = "$t6" # convenios
t7 = "$t7" # convenios
t8 = "$t8" 
t9 = "$t9" 

#Arguments Registers
a0 = "$a0"
a1 = "$a1"
a2 = "$a2"
a3 = "$a3"

#frame pointer
fp = "$fp"
#stack pointer
sp = "$sp"

ra = "$ra"
lo = "lo"
hi = "hi"
v0 = "$v0"
s0 = "$s0"
s1 = "$s1"
s2 = "$s2"
s3 = "$s3"
zero = "$zero"

SYSCALL_PRINT_INT = 1
SYSCALL_PRINT_STR = 4
SYSCALL_READ_INT = 5
SYSCALL_READ_STR = 8
SYSCALL_SBRK = 9
SYSCALL_EXIT = 10

class MemoryManager:
    def __init__(self):
        self.all_reg = [t0,t1,t2,t3,t4,t5,t6,t7,t8,t9]
        self.used_reg = []
        self.stored = []
        
    def get_unused_reg(self):
        unused = list(set(self.all_reg) - set(self.used_reg)) + list(set(self.used_reg) - set(self.all_reg))
        reg = random.choice(unused)     
        self.used_reg.append(reg)
        return reg
    
    def clean(self):
        self.used_reg = self.stored
        self.stored = []
        
    def save(self):
        self.stored = self.used_reg.copy()
        


class MIPSBuilder:
    def __init__(self,errors):
        self.mips_code = ""
        self.main_procedure = mips.ProcedureNode("main")
        self.current_procedure = self.main_procedure
        self.text = [self.main_procedure]
        self.data = []
        self.params = []
        self.locals = []
        self.types = dict()
        self.attr_offset = dict()
        self.memo = MemoryManager()
    
    
    def get_offset(self,x):
        if x in self.locals:
            index = self.locals.index(x)
            return -4*index
        elif x in self.params:
            index = self.params.index(x)
            return (-4 * (len(self.locals)+len(self.params)))-4
    
    def register_instruction(self, instruction_type, *args):
        instruction = instruction_type(*args)
        self.current_procedure.instructions.append(instruction)    
        
    def register_data(self,data_type,*args):
        data = data_type(*args)
        self.data.append(data)
      
        
    def register_push(self, reg):
        self.register_instruction(mips.StoreWordNode, reg, 0, sp)
        self.register_instruction(mips.AddiNode, sp, sp, -4)

    def register_pop(self, reg):
        self.register_instruction(mips.LoadWordNode, reg, 4, sp)
        self.register_instruction(mips.AddiNode, sp, sp, 4)    
    
    def generate_exception_messages(self):
        self.register_data(mips.DataTypeNode, ABORT_SIGNAL, '.asciiz', ['"Program execution aborted"'])
        self.register_data(mips.DataTypeNode, CASE_MISSMATCH, '.asciiz', ['"Execution of a case statement without a matching branch"'])
        self.register_data(mips.DataTypeNode, CASE_VOID, '.asciiz', ['"Case on void"'])
        self.register_data(mips.DataTypeNode, DISPATCH_VOID, '.asciiz', ['"Dispatch on void"'])
        self.register_data(mips.DataTypeNode, ZERO_DIVISION, '.asciiz', ['"Division by zero"'])
        self.register_data(mips.DataTypeNode, SUBSTR_OUT_RANGE, '.asciiz', ['"Substring out of range"'])
        self.register_data(mips.DataTypeNode, HEAP_OVERFLOW, '.asciiz', ['"Heap overflow"'])
    
    def generate_attr_offset(self,type):
        attributes = self.types[type].attributes
        
        for i,attr in attributes:
            self.attr_offset[attr] = 4(i+1)
            
        
    
    @visitor.on("node")
    def visit(self, node=None):
        pass
    
    @visitor.when(cil.ProgramNode)
    def visit(self, node):
        for type in node.types:
            self.visit(type)
        
        self.generate_attr_offset
        self.generate_exception_messages()
                
        for str_data in node.data:
            self.visit(str_data)
        
        for instruction in node.code:
            self.visit(instruction)
        
        
        return mips.ProgramNode(self.data,self.text)
        

    @visitor.when(cil.TypeNode)
    def visit(self, node):
        
        self.types[node.name] = node
        values = []
        for func in node.methods:
            values.append(func[1])
             
        self.register_data(mips.DataTypeNode,'.word',node.name,values)
        self.register_data(mips.DataTypeNode, f'{node.name}_cname','.asciiz', [f'"{node.name}"'])
        
        
        #Filling type type info
        #self.register_instruction(mips.CommentNode(f"Filling {node.name} VT"))
        #self.register_instruction(mips.LoadAddress,t0,node.name)
        #self.register_instruction(mips.LoadAddress,t1,f'{node.name}_cname')
        
        #self.register_instruction(mips.StoreWordNode,t1,TYPENAME_OFFSET,t0) 
        
        #Filling type VT
        #for i,func in enumerate(node.methods):
        #    offset = FUNCTION_OFFSET*i
        #    self.register_instruction(mips.LoadAddress,t1,func.name)
        #    self.register_instruction(mips.StoreWordNode,t1,offset,t0)
            
    @visitor.when(cil.DataNode)
    def visit(self, node):
        self.register_data(mips.DataTypeNode,'.ascii',node.vname,[node.value])

    
        
    @visitor.when(cil.ParamNode)
    def visit(self,node):
        self.memo.save()
        reg = self.memo.get_unused_reg()
        
        self.params.append(node.name)
        
        self.register_instruction(mips.LoadInmediate,reg,node.name)
        self.register_instruction(mips.StoreWordNode,reg,len(self.params)*4,fp)
        
        self.memo.clean()
        
    @visitor.when(cil.ArgNode)                                          
    def visit(self,node):
        self.memo.save()
        reg = self.memo.get_unused_reg()
        
        offset = self.get_offset(node.name)
        self.register_instruction(mips.LoadWordNode,reg,offset,fp)
        self.register_push(reg)
        
        
        self.memo.clean()
        
        
        
    @visitor.when(cil.FunctionNode)
    def visit(self,node):
        self.current_procedure = mips.ProcedureNode(node.name)

        self.register_instruction(mips.CommentNode,"Pushing $ra")
        self.register_push(ra)

        self.register_instruction(mips.CommentNode,"Saving $fp")
        self.register_push(fp)
        self.register_instruction(mips.CommentNode,"New $fp")
        self.register_instruction(mips.MoveNode, fp, sp)
        
        self.register_comment("Reserving space for locals")
        self.register_instruction(mips.AddiNode, sp, sp, -4*len(node.localvars))                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 

        self.register_instruction(mips.CommentNode("Executing instructions"))
        for inst in node.instructions:
            self.visit(inst)
            

        self.register_instruction(mips.CommentNode("Restoring saved $ra"))
        self.register_instruction(mips.LoadWordNode, ra, RA_OFFSET, fp)#stored $ra
       

        self.register_comment("Restoring saved $fp")
        self.register_instruction(mips.LoadWordNode, fp, OLD_FP_OFFSET, fp)#stored (old)$fp

        AR = 4*(len(node.localvars) + len(node.arguments) + 2)
        #AR = 4*(len(node.localvars) + 2)
        
        self.register_instruction(mips.CommentNode("Cleaning stack after call"))
        self.register_instruction(mips.AddiNode, sp, sp, AR)
        
        self.register_instruction(mips.CommentNode("Return jump"))
        self.register_instruction(mips.JumpRegister, ra)

        self.text.append(self.current_procedure)    
        
  
    @visitor.when(cil.LoadNode)
    def visit(self,node):
        self.memo.save()
        reg = self.memo.used_reg()
        
        if isinstance(node.msg,int):
            self.register_instruction(mips.LoadInmediate,reg,node.msg)
        else:
            self.register_instruction(mips.LoadAddress,reg,node.msg)
        
        offset = self.get_offset(node.dest)
        self.register_instruction(mips.StoreWordNode,reg,offset,fp)
        self.memo.clean()
    
        
    #All return value is saved in register a1    
    @visitor.when(cil.ReturnNode)
    def visit(self,node): 
        offset = self.get_offset()
        self.register_instruction(mips.LoadWordNode,a1,offset,fp)
            
    @visitor.when(cil.GotoNode)
    def visit(self,node):
        self.register_instruction(mips.UnconditionalJumpNode,node.label)
        
    
    
    @visitor.when(cil.AllocateNode)
    def visit(self,node):
        self.memo.save()
        _size = (len(self.types[node.type].attributes)+1)*4
        self.register_instruction(mips.LoadInmediate,v0,SYSCALL_SBRK)
        self.register_instruction(mips.LoadInmediate,a0,_size)
        self.register_instruction(mips.SyscallNode)
        
        dest_offset = self.get_offset(node.dest)
        self.register_instruction(mips.StoreWordNode,v0,dest_offset,fp)        
        
        reg = self.memo.get_unused_reg()
        self.register_instruction(mips.LoadAddress,reg,node.type)
        self.register_instruction(mips.StoreWordNode,reg,0,v0)
        
        
        self.memo.clean()
        
    @visitor.when(cil.AssignNode)
    def visit(self,node):
        self.save()
        
        reg = self.memo.get_unused_reg()
        
        source_offset = self.get_offset(node.source)
        dest_offset = self.get_offset(node.dest)
        
        self.register_instruction(mips.LoadWordNode,reg,source_offset,fp)
        
        self.register_instruction(mips.StoreWordNode,reg,dest_offset,fp)

        self.memo.clean()        
        
        
        
    
    @visitor.when(cil.PlusNode)
    def visit(self,node):
        self.save()
        
        reg1 = self.memo.get_unused_reg()
        reg2 = self.memo.get_unused_reg()
        reg3 = self.memo.get_unused_reg()
        
        self.register_instruction(mips.LoadInmediate,reg1,node.left)
        self.register_instruction(mips.LoadInmediate,reg2,node.right)
        
        self.register_instruction(mips.AddNode,reg3,reg1,reg2)
        
        offset = self.get_offset(node.dest)
        self.register_instruction(mips.StoreWordNode,reg3,offset,fp)
        
        self.memo.clean()
    
    @visitor.when(cil.MinusNode)
    def visit(self,node):
        self.save()
        
        reg1 = self.memo.get_unused_reg()
        reg2 = self.memo.get_unused_reg()
        reg3 = self.memo.get_unused_reg()
        
        self.register_instruction(mips.LoadInmediate,reg1,node.left)
        self.register_instruction(mips.LoadInmediate,reg2,node.right)
        
        self.register_instruction(mips.SubNode,reg3,reg1,reg2)
        
        offset = self.get_offset(node.dest)
        self.register_instruction(mips.StoreWordNode,reg3,offset,fp)
        
        self.memo.clean()
    
    @visitor.when(cil.RuntimeErrorNode)
    def visit(self,node):
        
        self.register_instruction(mips.CommentNode,"Printing Abort Message")
        self.register_instruction(mips.LoadAddress,a0,ABORT_SIGNAL)
        self.register_instruction(mips.LoadInmediate,v0,SYSCALL_PRINT_STR)
        self.register_instruction(mips.SyscallNode)
        
        self.register_instruction(mips.CommentNode,"Aborting execution")
        self.register_instruction(mips.LoadInmediate,v0,SYSCALL_EXIT)
        self.register_instruction(mips.SyscallNode)
                                                  
    #PENDIENTEEEEEEEE    
    @visitor.when(cil.CopyNode)
    def visit(self,node):     
        self.register_instruction(mips.CommentNode,"CopyNode")
        
        self.register_instruction(mips.CommentNode,"Printing Abort Message")
        self.register_instruction(mips.LoadAddress,a0,ABORT_SIGNAL)
        self.register_instruction(mips.LoadInmediate,v0,SYSCALL_PRINT_STR)
        self.register_instruction(mips.SyscallNode)
        
        self.register_instruction(mips.CommentNode,"Aborting execution")
        self.register_instruction(mips.LoadInmediate,v0,SYSCALL_EXIT)
        self.register_instruction(mips.SyscallNode)
    
    @visitor.when(cil.StaticCallNode)
    def visit(self,node):
        
        self.register_instruction(mips.JumpAndLink,node.function)
        
        dest_offset = self.get_offset()
        self.register_instruction(mips.StoreWordNode,a1,dest_offset,fp)
        
    @visitor.when(cil.GetAttribNode)
    def visit(self, node):
        self.memo.save()
        
        reg1 = self.memo.get_unused_reg()
        reg2 = self.memo.get_unused_reg()
        
        instance_offset = self.get_offset()
        self.register_instruction(mips.LoadWordNode,reg1,instance_offset,fp)
        
        attr_offs = self.attr_offset[node.attr]
        self.register_instruction(mips.LoadWordNode,reg2,attr_offs,reg1)
        
        dest_offs = self.get_offset()
        self.register_instruction(mips.StoreWordNode,reg2,dest_offs,fp)
        
    
    @visitor.when(cil.SetAttribNode)
    def visit(self, node):
        self.memo.save()
        reg1 = self.memo.get_unused_reg()
        reg2 = self.memo.get_unused_reg()
        
        instance_offset = self.get_offset(node.type)
        self.register_instruction(mips.LoadWordNode,reg1,instance_offset,fp)
        
        value_offset = self.get_offset(node.value)
        self.register_instruction(mips.LoadWordNode,reg2,value_offset,fp)
        
        attr_os = self.attr_offset[node.attr]
        self.register_instruction(mips.StoreWordNode,reg2,attr_os,reg1)

        self.memo.clean()
        
                
    #Incompleto
    @visitor.when(cil.TypeOfNode)
    def visit(self,node):
        self.memo.save()
        
        reg1 = self.get_offset()
        reg2 = self.get_offset()
        
    @visitor.when(cil.TypeNameNode)
    def visit(self,node):
        pass
    
    @visitor.when(cil.GotoIfNode)
    def visit(self,node):
        pass
    
    @visitor.when(cil.LocalNode)  #No hace falta
    def visit(self,node):
        pass
        
    
        
        
        
    