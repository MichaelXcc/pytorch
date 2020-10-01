from typing import Dict, List, Optional
from dataclasses import dataclass

# This class holds information about model metadata. Used to track
# information about where the selective build operator list comes
# from, and potentially which model each operator is used in.
@dataclass
class PyTorchModelMetadata:
    name: str
    version: Optional[str]

    @staticmethod
    def from_yaml(data: Dict[str, object]) -> 'PyTorchModelMetadata':
        name = data['name']
        assert isinstance(name, str)

        version: Optional[str] = None
        if 'version' in data:
            ver = data['version']
            assert isinstance(ver, str)
            version = ver

        return PyTorchModelMetadata(name, version)

    def __str__(self: 'PyTorchModelMetadata') -> str:
        if self.version is None:
            return self.name
        else:
            return "{}@{}".format(self.name, self.version)
        # end if

    def to_dict(self) -> Dict[str, object]:
        if self.version is None:
            return {
                'name': self.name,
            }
        else:
            return {
                'name': self.name,
                'version': self.version,
            }
        # end if



@dataclass(frozen=True)
class SelectiveBuildOperator():
    # The name of the operator. This includes the aten::, etc... prefix
    # The operator name may or may not have the overload name. If this
    # operator name does not specify an overload name, the way to determine
    # if this entry refers to the family of operators with this base name
    # or just the operator with this name is to look at the value of the
    # 'include_all_overloads' flag in this class.
    name: str

    # True if this is a root operator (i.e. called directly from TorchScript, etc...)
    is_root_operator: bool

    # Is this operator used for on-device training? If True, then we need to
    # use the information to generate code in VariableType_N.cpp for registration
    # of training related operators
    is_used_for_training: bool

    # If True, it indicates that this operator instance (object) refers to an
    # operator without the overload name and should apply to all overloads
    # which have this operator name as the base name. This flag is applicable
    # only for objects that have operator names without a DOT (period) character
    # in them.
    include_all_overloads: bool

    # The list of models that use this operator.
    models: Optional[List[PyTorchModelMetadata]]

    @staticmethod
    def from_yaml_dict(op_name: str, op_info: Dict[str, object]) -> 'SelectiveBuildOperator':
        is_root_operator = op_info.get('is_root_operator', True)
        assert isinstance(is_root_operator, bool)

        is_used_for_training = op_info.get('is_used_for_training', True)
        assert isinstance(is_used_for_training, bool)

        include_all_overloads = op_info.get('include_all_overloads', True)
        assert isinstance(include_all_overloads, bool)

        models: Optional[List[PyTorchModelMetadata]] = None
        if 'models' in op_info:
            models_list = op_info['models']
            assert isinstance(models_list, list)
            models = list(map(
                lambda x: PyTorchModelMetadata.from_yaml(x),
                models_list,
            ))

        return SelectiveBuildOperator(
            op_name,
            is_root_operator,
            is_used_for_training,
            include_all_overloads,
            models,
        )

    @staticmethod
    def from_legacy_operator_name_without_overload(name: str) -> 'SelectiveBuildOperator':
        return SelectiveBuildOperator(
            name,
            True,
            True,
            True,
            None,
        )

    def to_dict(self) -> Dict[str, object]:
        ret: Dict[str, object] = {
            'is_root_operator': self.is_root_operator,
            'is_used_for_training': self.is_used_for_training,
            'include_all_overloads': self.include_all_overloads,
        }
        if self.models is not None:
            models = list(map(lambda m: m.to_dict(), self.models))
            ret['models'] = models
        # end if
        return ret


def merge_model_lists(
        lhs: Optional[List[PyTorchModelMetadata]],
        rhs: Optional[List[PyTorchModelMetadata]],
) -> Optional[List[PyTorchModelMetadata]]:
    # Ensure that when merging, each model shows up just once.
    mdict = {}
    for model in (lhs or []) + (rhs or []):
        mdict[str(model)] = model
    # end for

    models = None
    if len(mdict) > 0:
        models = list(mdict.values())
    # end if

    return models


def combine_operators(
        lhs: 'SelectiveBuildOperator',
        rhs: 'SelectiveBuildOperator') -> 'SelectiveBuildOperator':
    if str(lhs.name) != str(rhs.name):
        raise Exception(
            "Expected both arguments to have the same name, but got '{}' and '{}' instead".format(
                str(lhs.name),
                str(rhs.name),
            )
        )

    return SelectiveBuildOperator(
        lhs.name,
        lhs.is_root_operator or rhs.is_root_operator,
        lhs.is_used_for_training or rhs.is_used_for_training,
        lhs.include_all_overloads or rhs.include_all_overloads,
        merge_model_lists(lhs.models, rhs.models),
    )

def merge_operator_dicts(
        lhs: Dict[str, SelectiveBuildOperator],
        rhs: Dict[str, SelectiveBuildOperator],
) -> Dict[str, SelectiveBuildOperator]:
    operators: Dict[str, SelectiveBuildOperator] = {}
    for (op_name, op) in list(lhs.items()) + list(rhs.items()):
        new_op = op
        if op_name in operators:
            new_op = combine_operators(operators[op_name], op)

        operators[op_name] = new_op

    return operators


def strip_operator_overload_name(op_name: str) -> str:
    return op_name.split(".")[0]