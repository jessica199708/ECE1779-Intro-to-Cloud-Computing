import boto3
from app import config
from datetime import datetime, timedelta


# Get CPU utilization of the worker in past 30 min from cloudwatch
def inst_CPU(inst_id):
    ec2 = boto3.resource('ec2')
    instance = ec2.Instance(inst_id) # Identify the instance by ID
    watch = boto3.client('cloudwatch')
    start = 31
    end = 30  # the fist time interval is 31 to 30
    CPU_utl = []     # A list to store CPU utilization in past 30 min
    for times in range(0, 30):
        CPU = watch.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='CPUUtilization',
                Dimensions=[
                    {
                        'Name': 'InstanceId',
                        'Value': instance.id
                    },
                ],
                StartTime=datetime.utcnow() - timedelta(seconds=start * 60),
                EndTime=datetime.utcnow() - timedelta(seconds=end * 60),
                Period=60,  # Every 60 sec get once data
                Statistics=['Average']
            )
        # Time interval shifts by 1 min
        start -= 1
        end -= 1
        utilization = 0  # Initialize utilization of each 1 min
        for data in CPU['Datapoints']:
            utilization = round(data['Average'], 2)  # Round off the float, keep 2 digits
        CPU_utl.append(utilization)  # Contain 30 CPU utilzations values


    x_axis =list(range(1, 31))
    return x_axis, CPU_utl


# Get HTTP request rate of the worker in past 30 min
def inst_HTTP(inst_id):
    ec2 = boto3.resource('ec2')
    instance = ec2.Instance(inst_id)
    watch = boto3.client('cloudwatch')
    start = 31
    end = 30  # fist time interval is 31 to 30
    http_rate = []  # A list to store HTTP request rate in past 30 min
    for times in range(0, 30):
        HTTP = watch.get_metric_statistics(
            Namespace='AWS/ApplicationELB',
            MetricName='RequestCountPerTarget',
            Dimensions=[
                {
                    'Name': 'TargetGroup',
                    'Value': config.target_group_dimension
                },
            ],
            StartTime=datetime.utcnow() - timedelta(seconds=start * 60),
            EndTime=datetime.utcnow() - timedelta(seconds=end * 60),
            Period=60,
            Statistics=['Sum']
        )
        start -= 1
        end -= 1
        http_count = 0  # Initialize HTTP request of each 1 min
        for data in HTTP['Datapoints']:
            http_count = int(data['Sum'])  # Save the count number as an integer
        http_rate.append(http_count)

        x_axis = list(range(1, 31))
    return x_axis, http_rate


# Count the number of workers in past 30 minutes
def number_workers():
    ec2 = boto3.resource('ec2')
    watch = boto3.client('cloudwatch')

    start = 31
    end = 30  # fist time interval is 31 to 30
    inst_num = []  # A list to store number of workers in past 30 min

    for times in range(0, 30):
        NUM_INSTANCES = watch.get_metric_statistics(
            Namespace='AWS/ApplicationELB',
            MetricName='HealthyHostCount',
            Dimensions=[
                {
                    'Name': 'TargetGroup',
                    'Value': config.target_group_dimension
                },
                {
                    'Name': 'LoadBalancer',
                    'Value': config.ELB_dimension
                }
            ],
            StartTime=datetime.utcnow() - timedelta(seconds=start * 60),
            EndTime=datetime.utcnow() - timedelta(seconds=end * 60),
            Period=60,
            Statistics=['Average']
        )

        for data in NUM_INSTANCES['Datapoints']:
            inst_count = int(data['Average'])  # Save the count number as an integer
            inst_num.append(inst_count)

        start -= 1
        end -= 1

    x_axis = list(range(0, len(inst_num)))

    return x_axis, inst_num


# Choose the running instances
def select_running_inst():
    ec2 = boto3.resource('ec2')
    # Find all running instances
    instances = ec2.instances.filter(
        Filters=[

            {'Name': 'placement-group-name',
             'Values': [config.placement_group]},

            {'Name': 'instance-state-name',
             'Values': ['running']},

            {'Name': 'image-id',
             'Values': [config.image_id]},

        ]
    )

    inst_id = []
    for instance in instances:
        inst_id.append(instance.id)  # List of the running instance IDs
    print('We have {} instances now!'.format(len(inst_id)))
    print(inst_id)
    return instances  # Return the running instances


# Get the lists for running instances, running&pending instances and healthy instances
# If the length of the three lists are equal, there is no pending and unhealthy instance in the target group
# continue run auto scaling per min

# If there exists any pending or unhealthy instance, we stop and do not auto scaling
# do not expand or shrink the worker pool size
# This function can make sure our auto scaling policy converges
def compare_inst():
    print('Now we are checking instances status!')

    ec2 = boto3.resource('ec2')
    instances = ec2.instances.filter(
        Filters=[

            {'Name': 'placement-group-name',
             'Values': [config.placement_group]},

            {'Name': 'instance-state-name',
             'Values': ['running', 'pending']}, #running&pending instance

            {'Name': 'image-id',
             'Values': [config.image_id]},

        ]
    )

    # Running&pending instance ID list
    running_pending_inst_id = []
    for instance in instances:
        running_pending_inst_id.append(instance.id)
    print('We have {} running/pending instances now!'.format(len(running_pending_inst_id)))

    # Running instance ID list
    instances_running = select_running_inst()
    running_inst_id = []
    for instance in instances_running:
        running_inst_id.append(instance.id)
    print('We have {} running instances now!'.format(len(running_inst_id)))

    # Healthy instance ID list
    healthy_inst_id = []
    elb = boto3.client('elbv2')  # Load Balancer
    for instance_id in running_inst_id:
        result = elb.describe_target_health(
            TargetGroupArn=config.target_group_arn,
            Targets=[
                {
                    'Id': instance_id,
                    'Port': 5000
                }
            ]
        )
        if (result['TargetHealthDescriptions'][0]['TargetHealth']['State'] == 'healthy'):
            healthy_inst_id.append(instance_id)
    print('We have {} healthy instances now!'.format(len(healthy_inst_id)))

    # Compare the length for three lists
    if (len(running_inst_id) == len(running_pending_inst_id) & len(healthy_inst_id) == len(running_inst_id)):
        return True
    else:
        return False


# Get the average CPU utilization in every two minutes and return the values for auto scaling
def average_CPU_uti(instances):
    CPU_utl = []
    instance_id = []

    for instance in instances:
        instance_id.append(instance.id)
        watch = boto3.client('cloudwatch')

        # CPU utilization in 2 min
        CPU = watch.get_metric_statistics(
            Namespace='AWS/EC2',
            MetricName='CPUUtilization',
            Dimensions=[
                {
                    'Name': 'InstanceId',
                    'Value': instance.id
                },
            ],
            StartTime=datetime.utcnow() - timedelta(seconds=2 * 60),
            EndTime=datetime.utcnow() - timedelta(seconds=0 * 60),
            Period=60,
            Statistics=['Average']
        )

        for data in CPU['Datapoints']:
            utilization = round(data['Average'], 2)
            CPU_utl.append(utilization)

    average_uti = sum(CPU_utl) / len(CPU_utl)
    print('List of CPU utilization from all running instances: ', CPU_utl)
    print('Average CPU utilization for entire worker group: ', average_uti)
    print('Running instance IDs: ', instance_id)
    return instance_id, average_uti


# Check whether the number of workers is in the range (1-8)
def full_load_check(instance_id):
    if len(instance_id) == 8:  # Full load
        print('Worker pool is fully loaded!', len(instance_id), 'instances are running.')

    elif len(instance_id) == 1:  # Minimum size
        print('Worker pool reached minimum size! only ', len(instance_id), 'instance is running.')


# Add one instance
def inst_add():
    ec2 = boto3.resource('ec2')
    instance = ec2.create_instances(ImageId=config.image_id,
                                    InstanceType='t2.medium',
                                    KeyName=config.key_pair,
                                    MinCount=1,
                                    MaxCount=1,
                                    Monitoring={'Enabled': True},
                                    Placement={'AvailabilityZone': 'us-east-1f',
                                               'GroupName': config.placement_group},
                                    SecurityGroups=[config.security_group],
                                    UserData=config.user_data,
                                    TagSpecifications=[
                                        {
                                            'ResourceType': 'instance',
                                            'Tags': [
                                                {
                                                    'Key': 'Name',
                                                    'Value': 'manually_add_worker'
                                                }
                                            ]
                                        }
                                    ],
                                    IamInstanceProfile={'Arn': config.iam_arn}
                                    )
    instance = instance[0]  # Increase one instance
    print('New instance', instance, ' is added.')

    instance.wait_until_running(
        Filters=[
            {
                'Name': 'instance-id',
                'Values': [instance.id]
            },
        ],
    )
    print('New Instance', instance, ' is running')

    elb = boto3.client('elbv2')
    print('Registering the new instance to ELB target group')
    elb.register_targets(
        TargetGroupArn=config.target_group_arn,
        Targets=[
            {
                'Id': instance.id,
            },
        ]
    )

    waiter = elb.get_waiter('target_in_service')
    waiter.wait(
        TargetGroupArn=config.target_group_arn,
        Targets=[
            {
                'Id': instance.id,
            },
        ],
    )
    print('New instance ', instance.id, 'is registered')


# Remove the targeted instance
def inst_remove(inst_Id):
    ec2 = boto3.resource('ec2')
    print('Deregistering instance-ID:', inst_Id)
    elb = boto3.client('elbv2')
    elb.deregister_targets(
        TargetGroupArn=config.target_group_arn,
        Targets=[
            {
                'Id': inst_Id,
            },
        ]
    )

    waiter = elb.get_waiter('target_deregistered')
    waiter.wait(
        TargetGroupArn=config.target_group_arn,
        Targets=[
            {
                'Id': inst_Id,
            },
        ],
    )
    print('Instance-ID: ', inst_Id, 'is deregistered')
    print('Terminating instance-ID:', inst_Id)

    instance = ec2.instances.filter(InstanceIds=[inst_Id])
    if instance is not None:
        for inst in instance:
            inst.terminate()
            inst.wait_until_terminated(
                Filters=[
                    {
                        'Name': 'instance-id',
                        'Values': [inst.id]
                    },
                ],
            )
            print('Instance-ID: ', inst.id, ' is terminated')