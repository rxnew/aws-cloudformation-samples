import json

import pytest

from src import index


@pytest.fixture()
def macro_event():
    return {
        'region': 'ap-northeast-1',
        'accountId': '111111111111',
        'params': {},
        'fragment': {
            'AWSTemplateFormatVersion': '2010-09-09',
            'Outputs': {
                'TestResourceArnList': {
                    'Value': {
                        'Fn::Join': [
                            ',',
                            {
                                'Fn::GetAtt': 'TestResource.Arn',
                            },
                        ],
                    },
                },
            },
            'Resources': {
                'TestResource': {
                    'Type': 'List<AWS::Test::Test>',
                    'Metadata': {
                        'TempLoop::Iteration': {
                            'Ref': 'Names',
                        },
                    },
                    'Properties': {
                        'Name': {
                            'Ref': 'TempLoop::Item',
                        },
                        'Description': {
                            'Fn::Sub': 'resource-${TempLoop::Item}',
                        },
                    },
                },
            },
            'Description': 'description',
            'Parameters': {
                'Names': {
                    'Type': 'CommaDelimitedList',
                },
            },
        },
        'transformId': 'yyyy',
        'requestId': 'xxxx',
        'templateParameterValues': {
            'Names': ['test1', 'test2', 'test3'],
        },
    }


def test_handler(macro_event, mocker):
    ret = index.handler(macro_event, {})

    resources = ret['fragment']['Resources']
    assert len(resources) == 3

    resource1 = resources[index.Processor._make_resource_name('TestResource', 0)]
    assert resource1['Properties']['Name'] == 'test1'
    assert resource1['Properties']['Description'] == 'resource-test1'
    assert 'Metadata' not in resource1

    output = ret['fragment']['Outputs']
    assert len(output['TestResourceArnList']['Value']['Fn::Join'][1]) == 3


def test_eval():
    params = {
        'RoleName': 'test-role',
        'Effect': 'Allow',
    }
    test_role_props = {
        'RoleName': {
            'Ref': 'RoleName',
        },
        'AssumeRolePolicyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Effect': '!Ref Effect',
                    'Principal': {
                        'Service': 'lambda.amazonaws.com',
                    },
                    'Action': 'sts:AssumeRole',
                }
            ]
        }
    }
    ret = index.Evaluator(index.Ref(params)).eval(test_role_props)
    assert ret['RoleName'] == params['RoleName']
    assert ret['AssumeRolePolicyDocument']['Statement'][0]['Effect'] == params['Effect']
