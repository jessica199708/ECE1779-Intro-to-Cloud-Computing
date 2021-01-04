from app import app
from flask import render_template, url_for, flash, redirect, request
import boto3
from app import config
from datetime import datetime, timedelta
import io
import matplotlib.pyplot as plt
import base64
from app import auto_scaling
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import time
import requests
from app.form import autoscalingForm, Photo, User
from app import db
from app import manager

# Scheduler to run in the background inside the application
scheduler = BackgroundScheduler()
# Controls whether the scheduler thread is daemonic or not
# False:  the scheduler must be shut down explicitly when the program is about to finish
# or it will prevent the program from terminating.
scheduler.daemonic = False


# response = requests.get('http://169.254.169.254/latest/meta-data/iam/security-credentials/S3FullAccess')
# data = response.json()
# AccessKeyId = data['AccessKeyId']
# SecretAccessKey = data['SecretAccessKey']
# Token = data['Token']


@app.before_first_request
# Automatically check if any instance exists.
# Resize the worker pool size to 1
# If no instance exists, create one
# If more than one instance, delete to one
def auto_check():
    print('Auto check begins!')
    ec2 = boto3.resource('ec2')
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
        inst_id.append(instance.id)

    if (len(inst_id)>1):
        print('We have {} instance! Resize to one!'.format(len(inst_id)))
        for i in range(1, len(inst_id)):
            manager.inst_remove(inst_id[i])
            print('We removed instance: {}!'.format(inst_id[i]))

    elif (inst_id == []):
        print('There is no running instance! Create ONE!')
        manager.inst_add()


# Do auto scaling per min
@app.before_first_request
def auto_scale():
    scheduler.add_job(func=auto_scaling.auto_handler, trigger="interval", seconds=60, max_instances=100)
    scheduler.start()


# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())


# Home page: display the number of instances in past 30 minutes
@app.route('/')
@app.route('/home')
def home():
    x_axis, inst_num = manager.number_workers()
    plt.plot(x_axis, inst_num, marker='*')
    plt.xlabel('Time (minutes)', fontsize=12)
    plt.ylabel('Instance number', fontsize=12)
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close()
    buf.seek(0)
    buffer = b''.join(buf)
    b2 = base64.b64encode(buffer)  # Encode and decode image
    instance_num_image = b2.decode('utf-8')
    return render_template('home.html', instance_num=instance_num_image)


# Worker control page: increase workers or decrease workers
@app.route('/worker_control')
def worker_control():
    title = 'Change Workers'
    return render_template('worker_control.html', title=title)


@app.route('/increase_workers', methods=['GET', 'POST'])
def increase_workers():
    ec2 = boto3.resource('ec2')
    instances = ec2.instances.filter(
        Filters=[

            {'Name': 'placement-group-name',
             'Values': [config.placement_group]},

            {'Name': 'instance-state-name',
             'Values': ['running']},  # filter running instances

            {'Name': 'image-id',
             'Values': [config.image_id]},
        ]
    )

    inst_id = []
    for instance in instances:
        inst_id.append(instance.id)
    print('Worker pool has ', len(inst_id), " running instances!")
    if len(inst_id) >= 8:
        print('Worker pool is fully loaded! ', len(inst_id), " are running!")

    instance = ec2.create_instances(ImageId=config.image_id,
                                    InstanceType='t2.medium',
                                    KeyName=config.key_pair,
                                    MinCount=1,
                                    MaxCount=1,  # add one instance per time
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
    instance = instance[0]  # only one instance in the instance list
    print('New instance', instance, ' is added.')

    # Wait until the instance runs
    instance.wait_until_running(
        Filters=[
            {
                'Name': 'instance-id',
                'Values': [instance.id]
            },
        ],
    )
    print('New Instance', instance, ' is running')

    elb = boto3.client('elbv2')  # Load Balancer
    print('Registering the new instance to ELB target group')
    # Registers the specific targets with the specific target group
    elb.register_targets(
        # Register targets with a target group by instance ID
        TargetGroupArn=config.target_group_arn,  # ARN of the target group
        Targets=[
            {
                'Id': instance.id,
            },
        ]
    )

    # Waiting for register success
    # Returns an object that can wait for some condition
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

    return redirect(url_for('worker_control'))


@app.route('/decrease_workers', methods=['GET', 'POST'])
def decrease_workers():
    ec2 = boto3.resource('ec2')
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
    # Select the running instances
    inst_id = []
    for instance in instances:
        inst_id.append(instance.id)

    # If there are more than one running instances, remove the oldest one
    if len(inst_id) > 1:
        inst_Id = inst_id[0]  # instance ID of the removing instance
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
        print('Instance-ID: ', inst_Id, 'is deregistered!')

        print('Terminating instance-ID:', inst_Id)
        # Check whether the instance can be found by its ID
        instance = ec2.instances.filter(InstanceIds=[inst_Id])
        if instance is not None:
            for inst in instance:
                inst.terminate()
                # Waits until the instance is terminated
                inst.wait_until_terminated(
                    Filters=[
                        {
                            'Name': 'instance-id',
                            'Values': [inst.id]
                        },
                    ],
                )
                print('Instance-ID: ', inst.id, ' is terminated')

    return redirect(url_for('worker_control'))


# Plot the CPU utilization and HTTP request for each running instance
@app.route('/<instance_id>', methods=['GET', 'POST'])
def view(instance_id):
    time_list, cpu_list = manager.inst_CPU(instance_id)
    list_time, http_list = manager.inst_HTTP(instance_id)
    plt.plot(time_list, cpu_list, marker='*')
    plt.xlabel('Time (minutes)', fontsize=12)
    plt.ylabel('CPU utilization (%)', fontsize=12)
    buf_CPU = io.BytesIO()
    plt.savefig(buf_CPU, format='png')
    plt.close()
    buf_CPU.seek(0)
    buffer = b''.join(buf_CPU)
    b2 = base64.b64encode(buffer)
    CPU_img = b2.decode('utf-8')

    plt.plot(list_time, http_list, marker='*')
    plt.xlabel('Time (minutes)', fontsize=12)
    plt.ylabel('Http request(Count)', fontsize=12)
    buf_HTTP = io.BytesIO()
    plt.savefig(buf_HTTP, format='png')
    plt.close()
    buf_HTTP.seek(0)
    buffer2 = b''.join(buf_HTTP)
    b3 = base64.b64encode(buffer2)
    HTTP_img = b3.decode('utf-8')

    return render_template('workers.html', instance_id=instance_id, CPU_img=CPU_img, HTTP_img=HTTP_img)


# Worker list page: select each running instance and show the details in worker_list.html
@app.route('/worker_list')
def worker_list():
    instance = manager.select_running_inst()
    return render_template('worker_list.html',  instance_list=instance)


# Manually set the threshold and ratio for auto scaling, and save in database
@app.route("/auto_modify", methods=['GET', 'POST'])
def auto_modify():
    if request.method == 'POST':
        threshold_max = request.form['threshold_max']
        threshold_min = request.form['threshold_min']
        ratio_expand = request.form['ratio_expand']
        ratio_shrink = request.form['ratio_shrink']

        u = autoscalingForm(threshold_max=threshold_max,
                            threshold_min=threshold_min,
                            ratio_expand=ratio_expand,
                            ratio_shrink=ratio_shrink)
        db.session.add(u)
        db.session.commit()  # add to the database

        return render_template("auto_modify.html", success = True)
    else:
        return render_template("auto_modify.html")


# Delete all user data in database and S3 bucket
@app.route('/clear_all_data')
def clear_all_data():
    # s3_resource = boto3.resource('s3', aws_access_key_id=AccessKeyId, aws_secret_access_key=SecretAccessKey, aws_session_token=Token)
    s3_resource = boto3.resource('s3')
    bucket = s3_resource.Bucket(config.BUCKET_NAME)
    bucket.objects.all().delete()
    db.session.query(User).delete()
    db.session.query(Photo).delete()
    db.session.commit()
    return render_template("clear_all_data.html")


# Terminate all workers, then stop manager instance
@app.route('/terminate_stop')
def terminate_stop():
    jobs = scheduler.get_jobs()
    jobs[0].remove()
    ec2 = boto3.resource('ec2')
    instances = manager.select_running_inst()  # Get all running workers
    id_to_remove = []
    for instance in instances:
        id_to_remove.append(instance.id)  # IDs of all running workers

    # Terminate all running instance
    for id in id_to_remove:
        manager.inst_remove(id)

    # Stop the manager instance
    instance = ec2.instances.filter(InstanceIds=['i-088e96273f0ee4d4a']) # Manager instance ID
    instance.stop()

    print('Manager instance is stopped!')

    return render_template("terminate_stop.html")

# Display load balancer DNS name
@app.route('/loadbalancerDNS')
def loadbalancerDNS():
    print('Display load balancer DNS name!')
    return render_template("loadbalancerDNS.html")
