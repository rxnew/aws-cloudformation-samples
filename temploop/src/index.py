import copy
import hashlib
import logging
import re
import traceback
from typing import Any, Dict, List, Optional, Union, Tuple

ITERATION_ATTR_NAME = 'TempLoop::Iteration'
ITERATION_ITEM_NAME = 'TempLoop::Item'
LIST_TYPE_REGEX = re.compile(r'List<(?P<name>.+)>')

Event = Dict[str, Any]
Resource = Dict[str, Any]
Output = Dict[str, Any]

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Event, context) -> Dict[str, Any]:
    try:
        event = Processor(event).process()
        return {
            'requestId': event['requestId'],
            'status': 'success',
            'fragment': event['fragment'],
        }
    except Exception as e:
        logger.error(e)
        print(traceback.format_exc())
        return {
            'requestId': event['requestId'],
            'status': 'fail',
            'fragment': event['fragment'],
        }


class Processor:
    def __init__(self, event: Event) -> []:
        self.event: Event = copy.deepcopy(event)
        self._resources: Dict[str, Resource] = self.event['fragment'].get('Resources', {})
        self._outputs: Dict[str, Output] = self.event['fragment'].get('Outputs', {})
        self._params: Dict[str, str] = Parameters(self.event).to_key_value()
        self._list_resources: Dict[str, List[str]] = {}
        self._ref: Ref = Ref(self._params)
        self._list_ref: ListRef = ListRef(self._list_resources)
        self._list_getattr: ListGetAtt = ListGetAtt(self._list_resources)
        self._range: Range = Range()
        self._processed = False

    def process(self) -> Event:
        if self._processed:
            return self.event
        self._processed = True

        new_resources = {}
        for k, v in self._resources.items():
            new_resources.update(self._expand(v, k))
        new_resources = {k: self._replace_resource_list_ref(v) for k, v in new_resources.items()}
        new_outputs = {k: self._replace_output_list_ref(v) for k, v in self._outputs.items()}
        self.event['fragment']['Resources'] = new_resources
        self.event['fragment']['Outputs'] = new_outputs
        return self.event

    def _expand(self, resource: Dict[str, Any], resource_name: str) -> Dict[str, Resource]:
        value_type = Processor._get_value_type(resource.get('Type', ''))
        if not value_type:
            return {resource_name: resource}

        iter_val = resource.get('Metadata', {}).get(ITERATION_ATTR_NAME)
        if iter_val is None:
            raise ValueError(f"Resource [{resource_name}] does not have 'Metadata.{ITERATION_ATTR_NAME}' attribute.")
        if type(iter_val) is list:
            objects = iter_val
        elif type(iter_val) is str or type(iter_val) is dict:
            objects = Evaluator(self._ref, self._range).eval(iter_val)
            if type(objects) is not list:
                raise ValueError('Invalid iteration parameter.')
        else:
            raise ValueError(f"Invalid type of '{ITERATION_ATTR_NAME}' attribute. [type: {type(iter_val)}]")

        resources = {
            Processor._make_resource_name(resource_name, i): Processor._make_resource(resource, value_type, v)
            for i, v in enumerate(objects)
        }
        self._list_resources[resource_name] = list(resources.keys())
        return resources

    @staticmethod
    def _make_resource_name(base_name: str, index: int) -> str:
        suffix = hashlib.md5((base_name + str(index)).encode('utf-8')).hexdigest()[:12].upper()
        return base_name + suffix

    @staticmethod
    def _make_resource(resource: Resource, resource_type: str, var: Any) -> Resource:
        built_in_params = {ITERATION_ITEM_NAME: var}
        props = Evaluator(
            Ref(built_in_params),
            GetAtt(built_in_params),
            Sub(built_in_params),
        ).eval(resource.get('Properties', {}))
        new_resource = copy.deepcopy(resource)
        new_resource['Properties'] = props
        new_resource['Type'] = resource_type
        del new_resource['Metadata'][ITERATION_ATTR_NAME]
        if not new_resource['Metadata']:
            del new_resource['Metadata']
        return new_resource

    @staticmethod
    def _get_value_type(type_name: str) -> Optional[str]:
        m = LIST_TYPE_REGEX.match(type_name)
        if not m:
            return None
        return m.group('name')

    def _replace_list_ref(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        return Evaluator(self._list_ref, self._list_getattr).eval(obj)

    def _replace_resource_list_ref(self, resource: Resource) -> Resource:
        props = resource.get('Properties', {})
        resource['Properties'] = self._replace_list_ref(props)
        return resource

    def _replace_output_list_ref(self, output: Output) -> Output:
        return self._replace_list_ref(output)


class Parameters:
    def __init__(self, event: Event):
        params = event['fragment'].get('Parameters', {})
        param_values = event.get('templateParameterValues', {})
        self._params = {
            k: {'Value': v.get('Default'), 'Type': v.get('Type', '')}
            for k, v in params.items()
        }

        for k, v in param_values.items():
            param = self._params.get(k)
            if not param:
                raise ValueError(f"Parameter [{k}] is not defined.")
            param['Value'] = v

    def get(self, name: str, default=None) -> Any:
        return self._params.get(name, default)

    def get_value(self, name: str, default=None) -> Any:
        return self.get(name, {}).get('Value', default)

    def get_type(self, name: str, default=None) -> Any:
        return self.get(name, {}).get('Type', default)

    def to_key_value(self) -> Dict[str, Any]:
        return {k: v['Value'] for k, v in self._params.items()}


class Fn:
    def eval(self, arg: Any) -> List[Any]:
        return []

    def name(self) -> str:
        return ''

    def short_name(self) -> str:
        return ''


class Ref(Fn):
    def __init__(self, params: Dict[str, Any]) -> []:
        self._params = params

    def eval(self, arg: Union[str, Any]) -> Any:
        if type(arg) is not str:
            raise ValueError('Invalid argument type.')

        return self._params.get(arg)

    def name(self) -> str:
        return 'Ref'

    def short_name(self) -> str:
        return 'Ref'


class GetAtt(Fn):
    def __init__(self, params: Dict[str, Any]) -> []:
        self._params = params

    def eval(self, arg: Union[str, Any]) -> Any:
        if type(arg) is not str:
            raise ValueError('Invalid argument type.')

        a = arg.split('.', 1)
        value = self._params.get(a[0])
        if value is None:
            return None
        if len(a) == 1:
            return value
        return value + '.' + a[1]

    def name(self) -> str:
        return 'Fn::GetAtt'

    def short_name(self) -> str:
        return 'GetAtt'


class Sub(Fn):
    def __init__(self, params: Dict[str, Any]) -> []:
        self._params = params

    def eval(self, arg: Union[str, Any]) -> Union[Dict[str, str], str]:
        if type(arg) is not str:
            raise ValueError('Invalid argument type.')

        names = re.findall(r'\${([^}]+)}', arg)
        value = arg
        unevaluated = False
        for name in names:
            param = self._params.get(name)
            if param is not None:
                value = value.replace('${' + name + '}', param)
            else:
                unevaluated = True
        return {self.name(): value} if unevaluated else value

    def name(self) -> str:
        return 'Fn::Sub'

    def short_name(self) -> str:
        return 'Sub'


class ListRef(Fn):
    def __init__(self, params: Dict[str, List[str]]) -> []:
        self._params = params

    def eval(self, arg: str) -> Optional[List[Dict[str, str]]]:
        if type(arg) is not str:
            raise ValueError('Invalid argument type.')

        param = self._params.get(arg)
        if param is None:
            return None
        return [{self.name(): v} for v in param]

    def name(self) -> str:
        return 'Ref'

    def short_name(self) -> str:
        return 'Ref'


class ListGetAtt(Fn):
    def __init__(self, params: Dict[str, List[str]]) -> []:
        self._params = params

    def eval(self, arg: str) -> Optional[List[Dict[str, str]]]:
        if type(arg) is not str:
            raise ValueError('Invalid argument type.')

        a = arg.split('.', 1)
        param = self._params.get(a[0])
        if param is None:
            return None
        suffix = '.' + a[1] if len(a) == 2 else ''
        return [{self.name(): v + suffix} for v in param]

    def name(self) -> str:
        return 'Fn::GetAtt'

    def short_name(self) -> str:
        return 'GetAtt'


class Range(Fn):
    def __init__(self) -> []:
        pass

    def eval(self, arg: Union[int, Tuple[int, int], Any]) -> List[int]:
        if type(arg) is not int and type(arg) is not tuple:
            raise ValueError('Invalid argument type.')

        return list(range(arg))

    def name(self) -> str:
        return 'Fn::Range'

    def short_name(self) -> str:
        return 'Range'


class Evaluator:
    def __init__(self, *fn_list: Fn) -> []:
        self._fn_dict = {
            fn.name(): fn.eval
            for fn in list(fn_list)
        }
        self._short_formula_regex_dict = {
            fn.name(): re.compile(r'^\s*!' + fn.short_name() + r'\s*(?P<arg>.*)\s*$')
            for fn in fn_list
        }

    def eval(self, obj: Any) -> Any:
        if type(obj) is str:
            return self._eval_str(obj)
        if type(obj) is list:
            return self._eval_list(obj)
        if type(obj) is dict:
            return self._eval_dict(obj)
        return obj

    def _eval_str(self, obj: str) -> Any:
        for name, regex in self._short_formula_regex_dict.items():
            m = regex.match(obj)
            if m:
                evaluated = self._fn_dict[name](m.group('arg'))
                if evaluated is not None:
                    return evaluated
        return obj

    def _eval_list(self, obj: List[Any]) -> Any:
        return [self.eval(v) for v in obj]

    def _eval_dict(self, obj: Dict[str, Any]) -> Any:
        if len(obj) == 1:
            for name, fn in self._fn_dict.items():
                if name in obj:
                    evaluated = fn(obj[name])
                    if evaluated is not None:
                        return evaluated
        return {k: self.eval(v) for k, v in obj.items()}
