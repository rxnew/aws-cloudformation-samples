import json

from index import handler

event = {
    'region': '<リージョン>',
    'accountId': '<AWSアカウントID>',
    'params': {},
    'fragment': {
        'AWSTemplateFormatVersion': '2010-09-09',
        'Outputs': {
            'TestResourceArnList': {
                'Value': {
                    'Fn::GetAtt': 'TestResource.Arn'
                }
            }
        },
        'Resources': {
            'TestResource': {
                'Type': 'List<AWS::Test::Test>',
                'Metadata': {
                    'TempLoop::Iteration': '!Ref ListParam',
                },
                'Properties': {
                    'TestProperty': 'test',
                    'TestLoopProperty': {
                        'Name': '!Ref TempLoop::Item',
                        'Test': {
                            'Fn::Sub': 'aaaa-${TempLoop::Item}-fewafew${TempLoop::Item}'
                        },
                        'Arn': {
                            'Ref': 'AWS::AccountId'
                        }
                    }
                }
            },
            'TestResourceHoge': {
                'Type': 'AWS::Test::Test1',
                'Properties': {
                    'TestRefProperty': '!Ref TestResource',
                    'TestGetAttProperty': '!GetAtt TestResource.Arn',
                    'TestSubProperty': '!Sub hoge-${TestResource.Name}-aaa',
                    'TestProperty': 'test'
                }
            }
        },
        'Description': '<テンプレートで指定したDescription>',
        'Parameters': {
            'ListParam': {
                'Type': 'CommaDelimitedList'
            }
        }
    },
    'transformId': '<AWSアカウントID>::<マクロ名>',
    'requestId': '<自動採番されたリクエストID>',
    'templateParameterValues': {
        'ListParam': ['test1', 'test2', 'test3']

    }
}

ret = handler(event, {})
print(json.dumps(ret, indent=2))
