from email import message
import cmp.nbpackage
import cmp.visitor as visitor

from ast_nodes import Node, ProgramNode, ExpressionNode
from ast_nodes import ClassDeclarationNode, FuncDeclarationNode, AttrDeclarationNode
from ast_nodes import VarDeclarationNode, AssignNode, CallNode
from ast_nodes import (
    AtomicNode,
    BinaryNode,
    ArithmeticOperation,
    ComparisonOperation,
    IfNode,
    LetNode,
    CaseNode,
    CaseItemNode,
    WhileNode,
    BlockNode,
    IsvoidNode,
)
from ast_nodes import (
    ConstantNumNode,
    VariableNode,
    InstantiateNode,
    PlusNode,
    MinusNode,
    StarNode,
    DivNode,
    NegNode,
    NotNode,
    EqualNode,
    BooleanNode,
    StringNode,
)
from cool_visitor import FormatVisitor

from cmp.semantic import SemanticError as SError
from cmp.semantic import Attribute, Method, Type
from cmp.semantic import VoidType, ErrorType, IntType
from cmp.semantic import Context

from cmp.semantic import Scope
from cmp.utils import find_least_type
import copy
from errors import TypeError, NameError, SemanticError, AttributeError

# some predefined errors
WRONG_SIGNATURE = 'Method "%s" already defined in "%s" with a different signature.'
SELF_IS_READONLY = 'Variable "self" is read-only.'
LOCAL_ALREADY_DEFINED = 'Variable "%s" is already defined in method "%s".'
INCOMPATIBLE_TYPES = 'Cannot convert "%s" into "%s".'
VARIABLE_NOT_DEFINED = 'Variable "%s" is not defined in "%s".'
INVALID_OPERATION = 'Operation is not defined between "%s" and "%s".'


class TypeChecker:
    def __init__(self, errors=[]):
        self.context = None
        self.current_type = None
        self.current_method = None
        self.errors = errors

    @visitor.on("node")
    def visit(self, node, scope=None):
        pass

    @visitor.when(ProgramNode)
    def visit(self, node):
        scope = Scope()
        self.context = copy.copy(node.context)

        #visit classes in order (from tree root to leaves)
        parent_children_dict = {}
        initial_nodes = []
        visited = {}
        self.class_to_visit = []
        self.class_visited = {}
        for declaration in node.declarations:
            try:
                visited[declaration.id.lex] # checking if visited
            except:
                visited[declaration.id.lex] = True
                self.class_visited[declaration.id.lex] = False
                self.class_to_visit.append(declaration)
                if declaration.parent is None or declaration.parent.lex in ["IO", "Int", "String", "Bool"]: # is node has no parent, mark it to visit it first later
                    initial_nodes.append(declaration)
                else:
                    try:
                        self.context.get_type(declaration.parent.lex)
                        try:
                            parent_children_dict[declaration.parent.lex].append(declaration)
                        except:
                            parent_children_dict[declaration.parent.lex] = [declaration]
                    except: # add declarations where parent is not defined
                        initial_nodes.append(declaration)

        for declaration in initial_nodes: # first visit root nodes
            self.visit(declaration, scope.create_child(), parent_children_dict)

        while self.class_to_visit: # visiting classes involved in ciclyc heritage
            declaration = self.class_to_visit[0]
            self.visit(declaration, scope.create_child(), parent_children_dict)
            

        self.context = None
        self.current_type = None
        self.current_method = None

        return scope

    @visitor.when(ClassDeclarationNode)
    def visit(self, node, scope, parent_children_dict):
        self.class_to_visit.remove(node)
        self.class_visited[node.id.lex] = True # arked class as visited

        self.current_type = self.context.get_type(node.id.lex)
        scope.define_variable("self", self.current_type)

        for attr in self.current_type.attributes:
            scope.define_variable(attr.name, attr.type)

        for feature in node.features:
            self.visit(feature, scope)
        
        try:
            children = parent_children_dict[node.id.lex]
            for child in children: # after initialization, each parent class visits its children (note the child scope creation) 
                if not self.class_visited[child.id.lex]:
                    self.visit(child, scope.create_child(), parent_children_dict)
        except:
            return

    @visitor.when(AttrDeclarationNode)
    def visit(self, node, scope):
        try:
            typex = self.context.get_type(node.type.lex)
        except SError as e:
            # ERROR already reported in type builder
            return ErrorType()

        if typex.name == "SELF_TYPE":
            typex = self.current_type


        if node.init_exp != None:
            init_expr_type = self.visit(node.init_exp, scope)

            if not init_expr_type.conforms_to(typex):
                line, col = node.token.location
                self.errors.append(TypeError(line, col,INCOMPATIBLE_TYPES % (init_expr_type.name, typex.name)))

        return typex

    @visitor.when(FuncDeclarationNode)
    def visit(self, node, scope):
        self.current_method = self.current_type.get_method(node.id.lex)
        method_return_type = self.current_method.return_type
        if method_return_type.name == "SELF_TYPE":
            method_return_type = self.current_type

        child_scope = scope.create_child()

        # ------------parameters most have differente names------------
        param_names = self.current_method.param_names
        param_types = self.current_method.param_types
        param_used = {}

        for i, param_name in enumerate(param_names):
            if param_name == "self":
                param_n, param_t = node.params[i]
                node_row, node_col = param_n.location # location of param name
                self.errors.append(
                    SemanticError(node_row, node_col ,f"'self' cannot be the name of a formal parameter.")
                )
            try:
                param_used[param_name]
                param_n, param_t = node.params[i]
                node_row, node_col = param_n.location
                self.errors.append(
                    SemanticError(node_row, node_col ,f"Formal parameter '{param_name}' multiply defined in method '{node.id.lex}'")
                )
            except:
                param_used[param_name] = True
                child_scope.define_variable(param_name, param_types[i])

        # -------------------------------------------------------------

        body_type = self.visit(node.body, child_scope)

        if not body_type.conforms_to(method_return_type):
            node_row, node_col = node.body.token.location
            self.errors.append(TypeError( node_row, node_col, f"Inferred return type '{body_type.name}' of method '{node.id.lex}' (the type of the last expression) does not conform to declared return type '{method_return_type.name}'."))

        if self.current_type.parent is not None:
            try:
                parent_method = self.current_type.parent.get_method(
                    self.current_method.name
                )
                # ensure same return type of redefined method
                if parent_method.return_type != self.current_method.return_type:
                    node_row, node_col = node.type.location
                    self.errors.append(SemanticError(node_row, node_col, f"In redefined method '{node.id.lex}', return type {self.current_method.return_type.name} is different from original return type {parent_method.return_type.name}."))
                
                # redefined method most have same number of parameters
                if len(parent_method.param_names) != len(self.current_method.param_names):
                    node_row, node_col = node.id.location
                    self.errors.append(SemanticError(node_row, node_col, f"Incompatible number of formal parameters in redefined method '{node.id.lex}'."))                    
                    len_parent_params = len(parent_method.param_names)
                    len_current_params = len(self.current_method.param_names)
                    if len_current_params >= len_parent_params:
                        max_len = len_parent_params
                    else:
                        max_len = len_current_params
                else:
                    max_len = len(parent_method.param_names)

                # check that each param has the same type as in the original method
                for i in range(0, max_len):
                    if self.current_method.param_types[i] != parent_method.param_types[i]:
                        param_i_name, param_i_type = node.params[i]
                        node_row, node_col = param_i_name.location
                        self.errors.append(SemanticError(node_row, node_col, f"In redefined method '{node.id.lex}', type {self.current_method.param_types[i].name} of parameter {param_i_name.lex} is different from original type {parent_method.param_types[i].name}."))                    
                    
            except SError:
                pass # parent has no method named like this

        try:
            return_type = self.context.get_type(node.type.lex)
            if return_type.name == "SELF_TYPE":
                return self.current_type

            return return_type

        except SError as e:
            # Error already reported in type builder
            return ErrorType()

    @visitor.when(AssignNode)
    def visit(self, node, scope):
        if node.id.lex == "self":
            node_row, node_col = node.token.location
            self.errors.append(SemanticError(node_row, node_col, "Cannot assign to 'self'. " + SELF_IS_READONLY))
        var_type = None
        if not scope.is_defined(node.id.lex):
            node_row, node_col = node.id.location
            self.errors.append(
                NameError(node_row, node_col, VARIABLE_NOT_DEFINED % (node.id.lex, self.current_method.name))
            )
            var_type = ErrorType()
        else:
            var_type = scope.find_variable(node.id.lex).type

        expr_type = self.visit(node.expr, scope)
        if not expr_type.conforms_to(var_type):
            node_row, node_col = node.token.location
            self.errors.append(TypeError(node_row, node_col, f"Inferred type {expr_type.name} of assigned expression does not conforms to type {var_type.name} of variable '{node.id.lex}'"))

        return expr_type

    @visitor.when(CallNode)
    def visit(self, node, scope):
        auto_type = self.context.get_type("AUTO_TYPE")
        typex = None
        if node.obj is not None:
            typex = self.visit(node.obj, scope)
            if typex == auto_type:
                return auto_type

        else:
            typex = self.current_type

        method = None
        try:
            if not( node.at_type is None):
                node_at_type = self.context.get_type(node.at_type.lex)
                method = node_at_type.get_method(node.id.lex)
                if not typex.conforms_to(node_at_type):
                    node_row, node_col = node.at_type.location # maybe in node.obj
                    self.errors.append(
                        TypeError(node_row, node_col, f"Expression type {typex.name} does not conform to declared static dispatch type {node_at_type.name}.")
                    )
                    return ErrorType()
            else:
                method = typex.get_method(node.id.lex)
        except SError as error:
            node_col, node_row = node.token.location
            self.errors.append(AttributeError(node_col, node_row ,error.text))
            return ErrorType()

        if len(method.param_names) != len(node.args):
            node_row, node_col = node.id.location
            self.errors.append(
               SemanticError(node_row, node_col, f"There is no definition of {method.name} that takes {len(node.args)} arguments ")
            )

        for arg, ptype in zip(node.args, method.param_types):
            arg_type = self.visit(arg, scope)
            if not arg_type.conforms_to(ptype):
                node_row, node_col = arg.token.location 
                self.errors.append(TypeError(node_row, node_col,f"In call of method {node.id.lex} parameter of type {arg_type.name} does not conforms to declared type {ptype.name}"))

        if method.return_type == self.context.get_type("SELF_TYPE"):
            return typex

        return method.return_type

    @visitor.when(IfNode)
    def visit(self, node, scope):
        predicate_type = self.visit(node.if_expr, scope)

        if predicate_type.name != "Bool" and predicate_type.name != "AUTO_TYPE":
            node_row, node_col = node.if_expr.token.location
            self.errors.append(
               TypeError(node_row, node_col, f"Expression after 'if' must be Bool, current type is {predicate_type.name}")
            )
            return ErrorType()

        then_type = self.visit(node.then_expr, scope)
        else_type = self.visit(node.else_expr, scope)

        least_type = find_least_type(then_type, else_type, self.context)
        return least_type

    @visitor.when(WhileNode)
    def visit(self, node, scope):
        condition_type = self.visit(node.condition, scope)
        bool_type = self.context.get_type("Bool")

        if condition_type != bool_type and condition_type.name != "AUTO_TYPE":
            node_row, node_col = node.condition.token.location
            self.errors.append(
                TypeError(node_row, node_col, f"Expression in 'while' condition must be bool, current type is {condition_type.name}")
            )
            return ErrorType()

        return self.context.get_type("Object")

    @visitor.when(BlockNode)
    def visit(self, node, scope):
        typex = None
        for expr in node.expression_list:
            typex = self.visit(expr, scope)

        return typex

    @visitor.when(LetNode)
    def visit(self, node, scope):

        child_scope = scope.create_child()

        for var_dec in node.identifiers:
            self.visit(var_dec, child_scope)

        return self.visit(node.body, child_scope)

    @visitor.when(VarDeclarationNode)
    def visit(self, node, scope):
        if node.id == "self":
            node_row, node_col = node.token.location
            self.errors.append(SemanticError(node_row, node_col, "'self' cannot be bound in a 'let' expression. " + SELF_IS_READONLY))

        static_type = None
        try:
            static_type = self.context.get_type(node.type.lex)
            if static_type.name == "SELF_TYPE":
                static_type = self.current_type

        except SError as e:
            node_row, node_col = node.type.location
            self.errors.append(
               TypeError(node_row, node_col, e.text)
            )
            static_type = ErrorType()

        if node.expr != None:
            typex = self.visit(node.expr, scope)
            if not typex.conforms_to(static_type):
                line, col = node.expr.token.location
                self.errors.append(TypeError(line, col, INCOMPATIBLE_TYPES % (typex.name, static_type.name)))

        scope.define_variable(node.id, static_type)
        return static_type

    @visitor.when(CaseNode)
    def visit(self, node, scope):
        self.visit(node.expr, scope)

        current_case_type = None
        case_types_found = []
        for item in node.case_items:
            if not (item.type.lex in case_types_found):
                case_types_found.append(item.type.lex)
                child_scope = scope.create_child()
                case_item_type = self.visit(item, child_scope)
                current_case_type = find_least_type(
                    current_case_type, case_item_type, self.context
                )
            else:
                line, col = item.type.location
                self.errors.append(SemanticError(line, col, f"Duplicate branch {item.type.lex} in case statement"))


        return current_case_type

    @visitor.when(CaseItemNode)
    def visit(self, node, scope):
        try:
            static_type = self.context.get_type(node.type.lex)
            scope.define_variable(node.id.lex, static_type)
        except SError as e:
            node_row, node_col = node.type.location
            self.errors.append(TypeError(node_row, node_col, f"Type {node.type.lex} of case branch is undefined."))

        typex = self.visit(node.expr, scope)

        return typex

    @visitor.when(InstantiateNode)  # NewNode
    def visit(self, node, scope):
        try:
            typex = self.context.get_type(node.lex.lex)
            if typex.name == "SELF_TYPE":
                return self.current_type
            return typex
        except SError as error:
            node_row, node_col = node.lex.location
            self.errors.append(TypeError(node_row, node_col, f"Type {node.lex.lex} of 'new' expression is not defined."))
            return ErrorType()

    @visitor.when(IsvoidNode)
    def visit(self, node, scope):
        self.visit(node.expr, scope)
        return self.context.get_type("Bool")

    @visitor.when(ArithmeticOperation)
    def visit(self, node, scope):
        int_type = self.context.get_type("Int")
        left_type = self.visit(node.left, scope)
        right_type = self.visit(node.right, scope)

        if (left_type != int_type and left_type.name != "AUTO_TYPE") or (
            right_type != int_type and right_type.name != "AUTO_TYPE"
        ):
            node_row, node_col = node.token.location
            self.errors.append(TypeError( node_row, node_col, INVALID_OPERATION % (left_type.name, right_type.name)))

        return int_type

    @visitor.when(ComparisonOperation)
    def visit(self, node, scope):
        int_type = self.context.get_type("Int")
        left_type = self.visit(node.left, scope)
        right_type = self.visit(node.right, scope)

        if (left_type != int_type and left_type.name != "AUTO_TYPE") or (
            right_type != int_type and right_type.name != "AUTO_TYPE"
        ):
            node_row, node_col = node.token.location
            self.errors.append(TypeError( node_row, node_col, INVALID_OPERATION % (left_type.name, right_type.name)))

        return self.context.get_type("Bool")

    @visitor.when(EqualNode)
    def visit(self, node, scope):
        int_type = self.context.get_type("Int")
        string_type = self.context.get_type("String")
        bool_type = self.context.get_type("Bool")
        built_in_types = [int_type, string_type, bool_type]

        left_type = self.visit(node.left, scope)
        right_type = self.visit(node.right, scope)

        if left_type in built_in_types or right_type in built_in_types:
            if (
                left_type != right_type
                and left_type.name != "AUTO_TYPE"
                and right_type.name != "AUTO_TYPE"
            ):
                node_row, node_col = node.token.location
                self.errors.append(
                    TypeError(node_row, node_col, f"One of the expressions of '=' operator is of type Int, String or Bool, the other must have the same static type. Left type: {left_type.name}. Right type: {right_type.name}")
                )

        return self.context.get_type("Bool")

    @visitor.when(NotNode)
    def visit(self, node, scope):
        bool_type = self.context.get_type("Bool")
        typex = self.visit(node.expr, scope)

        if typex != bool_type and not typex.name == "AUTO_TYPE":
            line, col = node.expr.token.location
            self.errors.append(
                TypeError(line, col, f"Expression after 'not' must be Bool, current is {typex.name}")
            )
            return ErrorType()

        return bool_type

    @visitor.when(NegNode)
    def visit(self, node, scope):
        int_type = self.context.get_type("Int")
        typex = self.visit(node.expr, scope)

        if typex != int_type and not typex.name == "AUTO_TYPE":
            node_row, node_col = node.expr.token.location
            self.errors.append(
                TypeError( node_row, node_col,f"Expression after '~' must be Int, current is {typex.name}")
            )
            return ErrorType()

        return int_type

    @visitor.when(ConstantNumNode)
    def visit(self, node, scope):
        return self.context.get_type("Int")

    @visitor.when(VariableNode)
    def visit(self, node, scope):
        var = scope.find_variable(node.lex)
        if var is None:
            node_row, node_col = node.token.location
            self.errors.append(
                NameError( node_row, node_col,VARIABLE_NOT_DEFINED % (node.lex, self.current_method.name))
            )
            return ErrorType()
        return var.type

    @visitor.when(StringNode)
    def visit(self, node, scope):
        return self.context.get_type("String")

    @visitor.when(BooleanNode)
    def visit(self, node, scope):
        return self.context.get_type("Bool")
