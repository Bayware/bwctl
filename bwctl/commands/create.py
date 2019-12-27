import os
import sys
from copy import deepcopy

import click
import yaml
from bwctl.actions.batch_spec import BatchSpec
from bwctl.actions.ssh_config import SshConfig
from bwctl.session.credentials import Credentials
from bwctl.utils.click import AliasedGroup
from bwctl.utils.common import log_info, log_error, log_ok, log_warn
from bwctl.utils.states import ObjectStatus, ObjectState, ObjectKind


@click.group('create', cls=AliasedGroup)
def create_cmd():
    """Create commands"""
    pass


@create_cmd.command(ObjectKind.BATCH.value)
@click.pass_context
@click.argument('filename')
@click.option('--input-format', required=False, type=click.Choice(['json', 'yaml']), default='yaml', show_default=True)
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
def create_batch(ctx, filename, input_format, dry_run):
    """Create batch"""
    log_info('Create batch: file={!r}, input=format={!r}, dry-run={!r}'.format(filename, input_format, dry_run))
    # Only YAML currently
    if input_format != 'yaml':
        log_warn('Only YAML supported')

    # Safely load YAML
    # noinspection PyBroadException
    try:
        with open(filename, 'r') as config_f:
            try:
                batch = yaml.safe_load(config_f)
            except yaml.YAMLError as err:
                log_error("Error while loading YAML: {0!r}".format(err))
                if hasattr(err, 'problem_mark'):
                    mark = err.problem_mark
                    log_error("Error position: ({}:{})".format(mark.line + 1, mark.column + 1))
                sys.exit(1)
        config_f.close()
    except IOError as err:
        log_error(err)
        sys.exit(1)
    except Exception:  # handle other exceptions such as attribute errors
        print("Unexpected error:", sys.exc_info()[0])
        sys.exit(1)

    # Parse batch
    try:
        batch = BatchSpec(batch, ctx.obj.state.api_version)
    except TypeError as err:
        log_error("Cannot parse batch: {0!r}".format(err))
        sys.exit(1)

    # Check batch API version
    if not batch.check_batch_version():
        log_error("Cannot create. Batch API version {!r} doesn't correspond current bwctl API version {!r}. Please "
                  "check batch file structure and modify it according to the current API version structure to make "
                  "bwctl working as expected".format(batch.batch_api_version, ctx.obj.state.api_version))
        sys.exit(1)

    # Get objects to be created (by fabric)
    create_target = {}
    for obj_kind in [ObjectKind.FABRIC, ObjectKind.VPC, ObjectKind.NODEBATCH, ObjectKind.WORKLOAD,
                     ObjectKind.PROCESSOR, ObjectKind.ORCHESTRATOR]:
        for obj in batch.get_attr_list(obj_kind):
            if obj_kind == ObjectKind.FABRIC:
                fabric_name = obj['metadata']['name']
            else:
                fabric_name = obj['metadata']['fabric']
            if fabric_name not in create_target:
                create_target[fabric_name] = {ObjectKind.FABRIC: [], ObjectKind.VPC: [],
                                              ObjectKind.NODEBATCH: [], ObjectKind.WORKLOAD: [],
                                              ObjectKind.PROCESSOR: [],
                                              ObjectKind.ORCHESTRATOR: []}
            create_target[fabric_name][obj_kind].append(batch.get_attr_name(obj))
    for fabric in create_target:
        for obj_kind in [ObjectKind.FABRIC, ObjectKind.VPC, ObjectKind.NODEBATCH, ObjectKind.WORKLOAD,
                         ObjectKind.PROCESSOR, ObjectKind.ORCHESTRATOR]:
            if obj_kind in create_target[fabric]:
                if create_target[fabric][obj_kind]:
                    log_info('{0}: {1!r}'.format(obj_kind.value.title(), create_target[fabric][obj_kind]))

    batch_result_success = True
    for fabric in create_target:
        if fabric in create_target[fabric][ObjectKind.FABRIC]:
            # Create fabric
            # Terraform zone start
            temp_state = deepcopy(ctx.obj.state)

            skip_fabric_create = False
            fabric_obj = [element for element in batch.get_attr_list(ObjectKind.FABRIC) if element['metadata']['name']
                          == fabric]
            log_info("Processing fabric {0!r}".format(fabric))
            # Check fabric exists
            if temp_state.check_fabric(fabric):
                new_fabric = temp_state.get_fabric(fabric)
                if not (temp_state.check_object_state(new_fabric, ObjectState.CREATED) and
                        temp_state.check_object_status(new_fabric, ObjectStatus.FAILED)):
                    log_warn('Fabric {0!r} already exist. Skipping fabric create'.format(fabric))
                    skip_fabric_create = True
            else:
                new_fabric = temp_state.get_clean_fabric()
            # Create fabric
            if not skip_fabric_create:
                log_info('Creating fabric {0!r}'.format(fabric))
                temp_state.set_object_state_status(new_fabric, ObjectState.CREATED, ObjectStatus.SUCCESS)
                temp_state.add_fabric(fabric, new_fabric)
                temp_state.fabric_create(fabric)
                ctx.obj.state = deepcopy(temp_state)
                ctx.obj.state.dump()
                if temp_state.check_object_status(temp_state.get_fabric(fabric), ObjectStatus.FAILED):
                    log_error("Fabric {0!r} creation failed. Skipping the rest...".format(fabric))
                    batch_result_success = False
                    continue
            # Check fabric is not already configured
            temp_state = deepcopy(ctx.obj.state)
            if temp_state.check_object_state(new_fabric, ObjectState.CREATED) or \
                    (temp_state.check_object_state(new_fabric, ObjectState.CONFIGURED) and
                     temp_state.check_object_status(new_fabric, ObjectStatus.FAILED)):
                log_info('Configure fabric {0!r}'.format(fabric))
                # Set ssh key if provided in batch or config
                skip_ssh_keygen = False
                ssh_key_name = None
                if 'privateKey' in fabric_obj[0]['spec']['sshKeys']:
                    if bool(fabric_obj[0]['spec']['sshKeys']['privateKey']):
                        skip_ssh_keygen = True
                        ssh_key_name = fabric_obj[0]['spec']['sshKeys']['privateKey']
                ssh_keys_cfg = ctx.obj.state.config.get_attr('ssh_keys')
                if 'private_key' in ssh_keys_cfg:
                    if not skip_ssh_keygen and bool(ssh_keys_cfg['private_key']):
                        skip_ssh_keygen = True
                        ssh_key_name = ssh_keys_cfg['private_key']
                if skip_ssh_keygen:
                    credentials = Credentials(fabric, temp_state, ctx.obj.state.config)
                    if not credentials.check_ssh(ssh_key_name):
                        log_error("Fabric {0!r} configuration failed. Skipping the rest...".format(fabric))
                        batch_result_success = False
                        continue
                    new_fabric['config']['sshKeys']['privateKey'] = ssh_key_name
                # Configure fabric
                # Check if company name is provided
                if 'companyName' in fabric_obj[0]['spec']:
                    company_name = fabric_obj[0]['spec']['companyName']
                else:
                    fabric_manager_cfg = ctx.obj.state.config.get_attr('fabric_manager')
                    if bool(fabric_manager_cfg['company_name']):
                        company_name = fabric_manager_cfg['company_name']
                    else:
                        log_error("Cannot configure fabric {!r}. Company name is required. Please run 'bwctl init' "
                                  "command or set 'fabric_manager.company_name' in {!r}. Skipping the rest..."
                                  .format(fabric, os.path.join(ctx.obj.state.config.dir, ctx.obj.state.config.file)))
                        batch_result_success = False
                        continue
                new_fabric['config']['companyName'] = company_name
                new_fabric['config']['credentialsFile'] = fabric_obj[0]['spec']['credentialsFile']
                temp_state.add_fabric(fabric, new_fabric)
                temp_state.fabric_configure(fabric, skip_ssh_keygen)
                ctx.obj.state = deepcopy(temp_state)
                ctx.obj.state.dump()
            else:
                log_warn('Fabric {0!r} already configured. Skipping fabric configure'.format(fabric))
            if temp_state.check_object_status(new_fabric, ObjectStatus.FAILED):
                log_error("Fabric {0!r} configuration failed. Skipping the rest...".format(fabric))
                batch_result_success = False
                continue
        vpc_index_list = {}
        temp_vpc_state = deepcopy(ctx.obj.state)
        vpc_list = create_target[fabric][ObjectKind.VPC][:]
        for vpc in vpc_list:
            # Generate VPC
            log_info("Processing VPC {0!r}".format(vpc))
            vpc_obj = [element for element in batch.get_attr_list(ObjectKind.VPC) if element['metadata']['name']
                       == vpc]
            if not temp_vpc_state.check_fabric(vpc_obj[0]['metadata']['fabric']):
                create_target[fabric][ObjectKind.VPC].remove(vpc)
                log_warn("Cannot proceed, fabric {0!r} does not exists, skipping...".format(fabric))
                continue
            vpc_cloud = vpc_obj[0]['spec']['cloud']
            # Check VPC exists
            if temp_vpc_state.check_vpc(fabric, vpc):
                new_vpc = temp_vpc_state.get_fabric_object(ObjectKind.VPC.value, vpc, fabric)
                if temp_vpc_state.check_object_state(new_vpc, ObjectState.CREATED) \
                        and temp_vpc_state.check_object_status(new_vpc, ObjectStatus.SUCCESS):
                    log_warn('VPC {0!r} already exist. Skipping VPC create'.format(vpc))
                    create_target[fabric][ObjectKind.VPC].remove(vpc)
                    continue
                vpc_index = new_vpc['index']
                log_info('VPC {0!r} is to be re-created'.format(vpc))
            else:
                # Get VPC index
                if vpc_cloud not in vpc_index_list:
                    vpc_index_list[vpc_cloud] = 1
                    cloud_vpc_list = [x for x in temp_vpc_state.get_fabric_objects(ObjectKind.VPC.value, fabric).items()
                                      if vpc_cloud in x[1]['cloud']]
                    if cloud_vpc_list:
                        vpc_index_list[vpc_cloud] = max(item[1]['index'] for item in cloud_vpc_list) + 1
                else:
                    vpc_index_list[vpc_cloud] += 1
                vpc_index = vpc_index_list[vpc_cloud]
                new_vpc = temp_vpc_state.get_clean_vpc()
                log_info('VPC {0!r} is to be created'.format(vpc))
            # State object creation
            new_vpc['cloud'] = vpc_cloud
            new_vpc['region'] = vpc_obj[0]['spec']['region']
            new_vpc['index'] = vpc_index
            new_vpc['properties'] = vpc_obj[0]['spec']['properties']
            temp_vpc_state.add_fabric_obj(fabric, ObjectKind.VPC.value, vpc, new_vpc)
        # Create VPCs action
        if create_target[fabric][ObjectKind.VPC]:
            log_info('Creating VPCs: {0!r}'.format(create_target[fabric][ObjectKind.VPC]))
            res = temp_vpc_state.vpc_create(fabric, create_target[fabric][ObjectKind.VPC])
            ctx.obj.state = deepcopy(temp_vpc_state)
            ctx.obj.state.dump()
            if not res[0]:
                sys.exit(res[1])

        # Generate node
        node_index_list = {}
        temp_node_state = deepcopy(ctx.obj.state)
        node_list = {ObjectKind.PROCESSOR: deepcopy(create_target[fabric][ObjectKind.PROCESSOR]),
                     ObjectKind.WORKLOAD: deepcopy(create_target[fabric][ObjectKind.WORKLOAD]),
                     ObjectKind.ORCHESTRATOR: deepcopy(create_target[fabric][ObjectKind.ORCHESTRATOR])}
        temp_nodes_list = {ObjectKind.PROCESSOR: deepcopy(create_target[fabric][ObjectKind.PROCESSOR]),
                           ObjectKind.WORKLOAD: deepcopy(create_target[fabric][ObjectKind.WORKLOAD]),
                           ObjectKind.ORCHESTRATOR: deepcopy(create_target[fabric][ObjectKind.ORCHESTRATOR])}
        orchestrator_in_batch = {'controller': False, 'telemetry': False, 'events': False}
        for obj_kind in node_list:
            for node in node_list[obj_kind]:
                node_obj = [item for item in batch.get_attr_list(obj_kind) if item['metadata']['name'] == node][0]
                if obj_kind == ObjectKind.ORCHESTRATOR:
                    orch_type = node_obj['spec']['type']
                    # Check for existing orch of same type in same fabric
                    orch_list = [x for x in temp_node_state.get_fabric_objects(obj_kind.value, fabric).items() if
                                 orch_type in x[1]['type'] and temp_node_state.check_object_status(x[-1],
                                 ObjectStatus.SUCCESS) and node != x[0]]

                    if orch_list:
                        log_warn("Orchestrator of type {0} exists in current fabric. "
                                 "Skipping orchestrator node creation".format(orch_type))
                        temp_nodes_list[obj_kind].remove(node)
                        continue
                    else:
                        if orchestrator_in_batch[orch_type]:
                            temp_nodes_list[obj_kind].remove(node)
                            continue
                        else:
                            orch_list = [item for item in batch.get_attr_list(obj_kind)
                                         if (item['spec']['type'] == orch_type and item['metadata']['name'] != node)]
                            if orch_list:
                                orchestrator_in_batch[orch_type] = True
                                log_warn("Orchestrator of type {0} placed in current batch more than once. "
                                         "Skipping duplicate entities".format(orch_type))
                node_vpc = node_obj['spec']['vpc']
                log_info("Processing node {0!r} in VPC {1!r}".format(node, node_vpc))
                # Check parent objects
                if not temp_node_state.check_fabric(node_obj['metadata']['fabric']):
                    temp_nodes_list[obj_kind].remove(node)
                    log_warn("Cannot proceed, fabric {0!r} does not exists, skipping...".format(fabric))
                    continue
                if not temp_node_state.check_vpc(fabric, node_vpc):
                    log_warn("Cannot proceed, VPC {0!r} does not exists, skipping...".format(node_vpc))
                    temp_nodes_list[obj_kind].remove(node)
                    continue
                # Check node exist
                if temp_node_state.check_nodeobj(fabric, node, obj_kind):
                    node_state_obj = temp_node_state.get_fabric_object(obj_kind.value, node, fabric)
                    if temp_node_state.check_object_state(node_state_obj, ObjectState.CREATED) and \
                            temp_node_state.check_object_status(node_state_obj, ObjectStatus.FAILED):
                        new_node = node_state_obj
                        node_index = node_state_obj['index']
                        log_info('Node {0!r} is to be re-created'.format(node))
                    else:
                        log_warn('Node {0!r} already exist. Skipping'.format(node))
                        temp_nodes_list[obj_kind].remove(node)
                        continue
                else:
                    # Get node index
                    if node_vpc not in node_index_list:
                        node_index_list[node_vpc] = {obj_kind: 1}
                        type_node_list = [x for x in temp_node_state.get_fabric_objects(obj_kind.value, fabric).items()
                                          if node_vpc in x[1]['vpc']]
                        if type_node_list:
                            node_index_list[node_vpc][obj_kind] = max(item[1]['index'] for item in type_node_list) + 1
                    else:
                        if obj_kind not in node_index_list[node_vpc]:
                            node_index_list[node_vpc][obj_kind] = 1
                            type_node_list = [x for x in
                                              temp_node_state.get_fabric_objects(obj_kind.value, fabric).items()
                                              if node_vpc in x[1]['vpc']]
                            if type_node_list:
                                node_index_list[node_vpc][obj_kind] = \
                                    max(item[1]['index'] for item in type_node_list) + 1
                        else:
                            node_index_list[node_vpc][obj_kind] += 1
                    new_node = temp_node_state.get_clean_nodeobj(obj_kind)
                    node_index = node_index_list[node_vpc][obj_kind]
                    log_info('Node {0!r} is to be created'.format(node))
                # State object creation
                new_node['vpc'] = node_vpc
                new_node['index'] = node_index
                if node_obj['spec']['properties'] is not None:
                    for property_key, property_val in deepcopy(node_obj['spec']['properties']).items():
                        new_node['properties'][property_key] = property_val
                new_node['properties']['dns_enabled'] = 'false'
                if obj_kind == ObjectKind.ORCHESTRATOR:
                    new_node['role'] = node_obj['spec']['role']
                    new_node['type'] = node_obj['spec']['type']
                temp_node_state.add_fabric_obj(fabric, obj_kind.value, node, new_node)

        # Generate objects from batches
        nodebatch_list = create_target[fabric][ObjectKind.NODEBATCH][:]
        for nodebatch in nodebatch_list:
            nodebatch_obj = [element for element in batch.get_attr_list(ObjectKind.NODEBATCH)
                             if element['metadata']['name'] == nodebatch]
            # Parse batch
            nodebatch_target = {}
            obj = {}
            for obj in nodebatch_obj[0]['spec']['template']:
                if obj['kind'].lower() == ObjectKind.WORKLOAD.value:
                    nodebatch_target[ObjectKind.WORKLOAD.value] = obj
                elif obj['kind'].lower() == ObjectKind.PROCESSOR.value:
                    nodebatch_target[ObjectKind.PROCESSOR.value] = obj
            log_info("Processing batch: {0!r}".format(nodebatch))
            nodebatch_vpc = obj['spec']['vpc']
            nodebatch_node_type = obj['kind'].lower()
            # Check parent objects
            if not temp_node_state.check_fabric(fabric):
                create_target[fabric][ObjectKind.NODEBATCH].remove(nodebatch)
                log_warn("Cannot proceed, fabric {0!r} does not exists, skipping...".format(fabric))
                continue
            if not temp_node_state.check_vpc(fabric, nodebatch_vpc):
                log_warn("Cannot proceed, VPC {0!r} does not exists, skipping...".format(nodebatch_vpc))
                create_target[fabric][ObjectKind.NODEBATCH].remove(nodebatch)
                continue
            # Set name of node
            node_types_list = {
                ObjectKind.PROCESSOR.value: 'p',
                ObjectKind.WORKLOAD.value: 'w'
            }
            if nodebatch_node_type in node_types_list:
                char_type = node_types_list[nodebatch_node_type]
            else:
                log_warn("Cannot proceed, node type {!r} is not supported in node batch, skipping..."
                         .format(nodebatch_node_type))
                continue
            # Check if there workload/processor in template
            nodebatch_workload_type = nodebatch_node_type
            nodebatch_state_created = False
            # Check if there is no nodebatch to resume
            if not temp_node_state.check_nodebatch(nodebatch):
                # Add batch to state
                nodebatch_state_obj = {nodebatch_node_type: {}}
                temp_node_state.set_object_state(nodebatch_state_obj, ObjectState.CREATED)
                temp_node_state.add_batch(nodebatch, nodebatch_state_obj)
                nodebatch_state_created = True
                log_info('No active node batch {!r} found, creating in state'.format(nodebatch))
                # Get node index
                nodebatch_node_vpc_list = [x for x in
                                           temp_node_state.get_fabric_objects(nodebatch_node_type, fabric).items() if
                                           nodebatch_vpc in x[1]['vpc']]
                nodebatch_node_index = 1
                if nodebatch_node_vpc_list:
                    nodebatch_node_index = max(item[1]['index'] for item in nodebatch_node_vpc_list) + 1
                # Generate nodes
                for i in range(nodebatch_obj[0]['spec']['instanceCount']):
                    node_name = nodebatch_vpc.split("-")[0] + '-' + char_type + '0' + str(nodebatch_node_index + i) \
                                + '-' + fabric
                    # Add node object to batch state
                    nb_node = dict(spec={'properties': {}}, metadata={}, kind=nodebatch_node_type)
                    nb_node['metadata']['fabric'] = fabric
                    nb_node['metadata']['name'] = node_name
                    nb_node['spec']['vpc'] = nodebatch_vpc
                    nb_node['spec']['config'] = deepcopy(nodebatch_target[nodebatch_node_type]['spec']['config'])
                    nb_node['state'] = nodebatch_target[nodebatch_node_type]['state']
                    temp_node_state.add_batch_obj(nodebatch, nodebatch_node_type, node_name, nb_node)
                    log_info('{0} {1!r} is added to processing'.format(nodebatch_node_type, node_name))
                ctx.obj.state = deepcopy(temp_node_state)
                ctx.obj.state.dump()
            if not nodebatch_state_created:
                log_info('Active node batch {!r} found in state, resuming'.format(nodebatch))
            # Processing nodes
            nodebatch_obj = temp_node_state.get_nodebatch(nodebatch)
            nodebatch_node_obj_list = [item[1] for item in nodebatch_obj[nodebatch_node_type].items()]
            nodebatch_node_list = [item['metadata']['name'] for item in nodebatch_node_obj_list]
            for node in nodebatch_node_list:
                node_obj = [item for item in nodebatch_node_obj_list if item['metadata']['name'] == node][0]
                node_vpc = node_obj['spec']['vpc']
                node_type = nodebatch_node_type
                log_info("Processing node: {0!r} in VPC {1!r}".format(node, node_vpc))
                temp_nodes_list[ObjectKind(node_type)].append(node)
                batch.add_to_attr_list(ObjectKind(node_type), node_obj)
                # Check parent objects
                if not temp_node_state.check_fabric(node_obj['metadata']['fabric']):
                    temp_nodes_list[ObjectKind(node_type)].remove(node)
                    log_warn("Cannot proceed, fabric {0!r} does not exists, skipping...".format(fabric))
                    continue
                if not temp_node_state.check_vpc(fabric, node_vpc):
                    log_warn("Cannot proceed, VPC {0!r} does not exists, skipping...".format(node_vpc))
                    temp_nodes_list[ObjectKind(node_type)].remove(node)
                    continue
                # Check node exist
                if temp_node_state.check_nodeobj(fabric, node, ObjectKind(node_type)):
                    node_state_obj = temp_node_state.get_fabric_object(node_type, node, fabric)
                    if temp_node_state.check_object_state(node_state_obj, ObjectState.CREATED) and \
                            temp_node_state.check_object_status(node_state_obj, ObjectStatus.SUCCESS):
                        log_warn('Node {0!r} already exist. Skipping'.format(node))
                        temp_nodes_list[ObjectKind(node_type)].remove(node)
                        if nodebatch_workload_type is not None:
                            if nodebatch_workload_type in nodebatch_obj:
                                create_target[fabric][ObjectKind(node_type)].append(node)
                                batch.add_to_attr_list(nodebatch_workload_type,
                                                       nodebatch_obj[nodebatch_workload_type][node])
                        continue
                    new_node = node_state_obj
                    node_index = node_state_obj['index']
                    log_info('Node {0!r} is to be re-created'.format(node))
                else:
                    # Get node index
                    if node_vpc not in node_index_list:
                        node_index_list[node_vpc] = {node_type: 1}
                        type_node_list = [x for x in temp_node_state.get_fabric_objects(node_type, fabric).items()
                                          if node_vpc in x[1]['vpc']]
                        if type_node_list:
                            node_index_list[node_vpc][node_type] = max(item[1]['index'] for item in type_node_list) + 1
                    else:
                        if node_type not in node_index_list[node_vpc]:
                            node_index_list[node_vpc][node_type] = 1
                            type_node_list = [x for x in temp_node_state.get_fabric_objects(node_type, fabric).items()
                                              if node_vpc in x[1]['vpc']]
                            if type_node_list:
                                node_index_list[node_vpc][node_type] = \
                                    max(item[1]['index'] for item in type_node_list) + 1
                        else:
                            node_index_list[node_vpc][node_type] += 1
                    new_node = temp_node_state.get_clean_nodeobj(ObjectKind(node_type))
                    node_index = node_index_list[node_vpc][node_type]
                    log_info('Node {0!r} is to be created'.format(node))
                # State object creation
                new_node['vpc'] = node_vpc
                new_node['index'] = node_index
                if node_obj['spec']['properties'] is not None:
                    for property_key, property_val in deepcopy(node_obj['spec']['properties']).items():
                        new_node['properties'][property_key] = property_val
                new_node['properties']['dns_enabled'] = 'false'
                temp_node_state.add_fabric_obj(fabric, node_type, node, new_node)
                # Add workload/processor to processing if present
                if nodebatch_workload_type is not None:
                    if nodebatch_workload_type in nodebatch_obj:
                        create_target[fabric][ObjectKind(node_type)].append(node)
                        batch.add_to_attr_list(nodebatch_workload_type, nodebatch_obj[nodebatch_workload_type][node])

        # Create nodes action
        nodes_list = []
        for obj_kind in temp_nodes_list:
            nodes_list = nodes_list + temp_nodes_list[obj_kind]
        if nodes_list:
            # Get credentials
            credentials = Credentials(fabric, temp_node_state.get(), ctx.obj.state.config)
            if not credentials.get():
                log_error('Cannot create objects. Not able to get credentials')
                sys.exit(1)
            log_info('Creating {0!r}'.format(nodes_list))
            if not temp_node_state.obj_create_check(fabric, temp_nodes_list):
                batch_result_success = False
                continue
            res = temp_node_state.obj_create(fabric, temp_nodes_list, credentials)
            if not res[0]:
                ctx.obj.state = deepcopy(temp_node_state)
                ctx.obj.state.dump()
                batch_result_success = False
                continue
            ctx.obj.state = deepcopy(temp_node_state)
            ctx.obj.state.dump()
            # Generate SSH configuration
            ssh_config = SshConfig(ctx.obj.state)
            if ssh_config.generate_config():
                log_info('Generating SSH config...')
            else:
                log_warn('Error during SSH config generation')

        # Check if batches are finished
        temp_node_state.nodebatch_check_success(create_target[fabric][ObjectKind.NODEBATCH], ObjectState.CREATED,
                                                ObjectKind.WORKLOAD)
        ctx.obj.state = deepcopy(temp_node_state)
        ctx.obj.state.dump()
        temp_node_state.nodebatch_check_success(create_target[fabric][ObjectKind.NODEBATCH], ObjectState.CREATED,
                                                ObjectKind.PROCESSOR)
        ctx.obj.state = deepcopy(temp_node_state)
        ctx.obj.state.dump()

        # Terraform zone end

        # Define action matrix
        def set_action_list(current_state, current_status, target_state, actions, entity, entity_role,
                            batch_entity_conf=None, state_entity_conf=None):
            """Sets actions for objects according current and target state"""
            if current_state == ObjectState.CREATED:
                if target_state == ObjectState.CONFIGURED:
                    actions['config'].append(entity)
                elif target_state == ObjectState.STARTED and (
                        entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]):
                    actions['config'].append(entity)
                    actions['start'].append(entity)
                elif target_state == ObjectState.STOPPED and (
                        entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]):
                    actions['config'].append(entity)
                    actions['stop'].append(entity)
            elif current_state == ObjectState.CONFIGURED:
                if target_state == ObjectState.CONFIGURED and current_status == ObjectStatus.FAILED:
                    actions['config'].append(entity)
                elif target_state == ObjectState.CONFIGURED and (
                        entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]
                        and batch_entity_conf != state_entity_conf):
                    actions['config'].append(entity)
                elif target_state == ObjectState.STARTED and (entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]
                                                              and batch_entity_conf != state_entity_conf):
                    actions['config'].append(entity)
                    actions['start'].append(entity)
                elif target_state == ObjectState.STARTED and (entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]
                                                              and current_status == ObjectStatus.FAILED):
                    actions['config'].append(entity)
                    actions['start'].append(entity)
                elif target_state == ObjectState.STARTED and (
                        entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]):
                    actions['start'].append(entity)
                elif target_state == ObjectState.STOPPED and (entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]
                                                              and batch_entity_conf != state_entity_conf):
                    actions['config'].append(entity)
                    actions['stop'].append(entity)
                elif target_state == ObjectState.STOPPED and (entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]
                                                              and current_status == ObjectStatus.FAILED):
                    actions['config'].append(entity)
                    actions['stop'].append(entity)
                elif target_state == ObjectState.STOPPED and (
                        entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]):
                    actions['stop'].append(entity)
            elif current_state == ObjectState.STARTED:
                if target_state == ObjectState.STARTED and current_status == ObjectStatus.FAILED:
                    actions['start'].append(entity)
                elif target_state == ObjectState.STARTED and (entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]
                                                              and batch_entity_conf != state_entity_conf):
                    actions['config'].append(entity)
                    actions['start'].append(entity)
                elif target_state == ObjectState.STOPPED and (entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]
                                                              and batch_entity_conf != state_entity_conf):
                    actions['config'].append(entity)
                    actions['stop'].append(entity)
                elif target_state == ObjectState.STOPPED:
                    actions['stop'].append(entity)
            elif current_state == ObjectState.STOPPED:
                if target_state == ObjectState.STOPPED and current_status == ObjectStatus.FAILED:
                    actions['stop'].append(entity)
                elif target_state == ObjectState.STOPPED and (entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]
                                                              and batch_entity_conf != state_entity_conf):
                    actions['config'].append(entity)
                    actions['stop'].append(entity)
                elif target_state == ObjectState.STARTED and (entity_role in [ObjectKind.WORKLOAD, ObjectKind.PROCESSOR]
                                                              and batch_entity_conf != state_entity_conf):
                    actions['config'].append(entity)
                    actions['start'].append(entity)
                elif target_state == ObjectState.STARTED:
                    actions['start'].append(entity)

        # Ansible zone start
        orch_actions = {'config': []}
        workload_actions = {'config': [], 'start': [], 'stop': []}
        processor_actions = {'config': [], 'start': [], 'stop': []}
        temp_state = deepcopy(ctx.obj.state)
        orch_list = create_target[fabric][ObjectKind.ORCHESTRATOR][:]
        for orch in orch_list:
            orch_obj = [element for element in batch.get_attr_list(ObjectKind.ORCHESTRATOR)
                        if element['metadata']['name'] == orch]
            log_info("Processing orchestrator {0!r}".format(orch))
            if not temp_state.check_fabric(orch_obj[0]['metadata']['fabric']):
                create_target[fabric][ObjectKind.ORCHESTRATOR].remove(orch)
                log_warn("Cannot proceed, fabric {0!r} does not exists, skipping...".format(fabric))
                continue
            if not temp_state.check_orchestrator(fabric, orch):
                # State object creation
                create_target[fabric][ObjectKind.ORCHESTRATOR].remove(orch)
                log_warn("Cannot proceed, orchestrator {0!r} does not exists, skipping...".format(orch))
                continue
            curr_obj = temp_state.get_fabric_object(ObjectKind.ORCHESTRATOR.value, orch, fabric)
            set_action_list(temp_state.get_object_state(curr_obj), temp_state.get_object_status(curr_obj),
                            ObjectState(orch_obj[0]['state']), orch_actions, orch, ObjectKind.ORCHESTRATOR)
            if not orch_actions['config']:
                log_warn('Orchestrator {0!r} already configured. Skipping'.format(orch))

        eng_list = create_target[fabric][ObjectKind.PROCESSOR][:]
        for eng in eng_list:
            eng_obj = [element for element in batch.get_attr_list(ObjectKind.PROCESSOR) if
                       element['metadata']['name'] == eng]
            log_info("Processing processor {0!r}".format(eng))
            if not temp_state.check_fabric(eng_obj[0]['metadata']['fabric']):
                create_target[fabric][ObjectKind.PROCESSOR].remove(eng)
                log_warn("Cannot proceed, fabric {0!r} does not exists, skipping...".format(fabric))
                continue
            if not temp_state.check_processor(fabric, eng):
                # State object check
                create_target[fabric][ObjectKind.PROCESSOR].remove(eng)
                log_warn("Cannot proceed, processor {0!r} does not exists, skipping...".format(eng))
                continue
            curr_obj = temp_state.get_fabric_object(ObjectKind.PROCESSOR.value, eng, fabric)
            batch_entity_config = temp_state.get_processor_spec_from_batch(eng_obj)
            state_entity_config = curr_obj['config']
            set_action_list(temp_state.get_object_state(curr_obj), temp_state.get_object_status(curr_obj),
                            ObjectState(eng_obj[0]['state']), processor_actions, eng, ObjectKind.PROCESSOR,
                            batch_entity_config, state_entity_config)
            if batch_entity_config != state_entity_config:
                curr_obj['config'] = batch_entity_config
            if not processor_actions['config'] and not processor_actions['start'] and not processor_actions['stop']:
                log_warn('Processor {0!r} already {1!r}. Skipping'.format(eng, eng_obj[0]['state']))

        workload_list = create_target[fabric][ObjectKind.WORKLOAD][:]
        for workload in workload_list:
            workload_obj = [element for element in batch.get_attr_list(ObjectKind.WORKLOAD) if
                            element['metadata']['name'] == workload]
            log_info("Processing workload {0!r}".format(workload))
            if not temp_state.check_fabric(workload_obj[0]['metadata']['fabric']):
                create_target[fabric][ObjectKind.WORKLOAD].remove(workload)
                log_warn("Cannot proceed, fabric {0!r} does not exists, skipping...".format(fabric))
                continue
            if not temp_state.check_workload(fabric, workload):
                # State object check
                create_target[fabric][ObjectKind.WORKLOAD].remove(workload)
                log_warn("Cannot proceed, workload {0!r} does not exists, skipping...".format(workload))
                continue
            curr_obj = temp_state.get_fabric_object(ObjectKind.WORKLOAD.value, workload, fabric)
            batch_entity_config = temp_state.get_workload_spec_from_batch(workload_obj)
            state_entity_config = curr_obj['config']
            set_action_list(temp_state.get_object_state(curr_obj), temp_state.get_object_status(curr_obj),
                            ObjectState(workload_obj[0]['state']), workload_actions, workload, ObjectKind.WORKLOAD,
                            batch_entity_config, state_entity_config)
            if batch_entity_config != state_entity_config:
                curr_obj['config'] = batch_entity_config
            if not workload_actions['config'] and not workload_actions['start'] and not workload_actions['stop']:
                log_warn('Workload {0!r} already {1!r}. Skipping'.format(workload, workload_obj[0]['state']))
        # Generate passwords
        passwd_controller = None
        passwd_grafana = None
        for orch in orch_actions['config']:
            if temp_state.get_fabric_object(ObjectKind.ORCHESTRATOR.value, orch, fabric).get('type') == 'controller':
                passwd_controller = temp_state.get_passwd()
            if temp_state.get_fabric_object(ObjectKind.ORCHESTRATOR.value, orch, fabric).get('type') == 'telemetry':
                passwd_grafana = temp_state.get_passwd()
        # Get dockerhub credentials
        orch_stop_batch = False
        credentials = None
        for orch in orch_actions['config']:
            if temp_state.get_fabric_object(ObjectKind.ORCHESTRATOR.value, orch, fabric).get('type') == 'controller':
                credentials = Credentials(fabric, temp_state.get(), ctx.obj.state.config)
                if not credentials.get_docker():
                    log_error('Cannot configure controller. Not able to get Bayware dockerhub credentials')
                    orch_stop_batch = True
        # Configure orchestrator action
        if orch_actions['config']:
            if not orch_stop_batch:
                log_info('Configuring orchestrators: {0!r}'.format(orch_actions['config']))
                res = temp_state.orchestrator_configure(fabric, orch_actions['config'],
                                                        controller_passwd=passwd_controller,
                                                        grafana_passwd=passwd_grafana, credentials=credentials)
                if not res[0]:
                    orch_stop_batch = True
                ctx.obj.state = deepcopy(temp_state)
                ctx.obj.state.dump()
        processor_stop_batch = False
        if not processor_stop_batch:
            if processor_actions['config']:
                log_info('Configuring processors: {0!r}'.format(processor_actions['config']))
                res = temp_state.processor_configure(fabric, processor_actions['config'])
                if not res[0]:
                    processor_stop_batch = True
                ctx.obj.state = deepcopy(temp_state)
                ctx.obj.state.dump()
            # Check if batches are finished
            temp_state.nodebatch_check_success(create_target[fabric][ObjectKind.NODEBATCH], ObjectState.CONFIGURED,
                                               ObjectKind.PROCESSOR)
            ctx.obj.state = deepcopy(temp_state)
            ctx.obj.state.dump()
        if not processor_stop_batch:
            if processor_actions['start']:
                log_info('Starting processors: {0!r}'.format(processor_actions['start']))
                res = temp_state.processor_start(fabric, processor_actions['start'])
                if not res[0]:
                    processor_stop_batch = True
                ctx.obj.state = deepcopy(temp_state)
                ctx.obj.state.dump()
            # Check if batches are finished
            temp_state.nodebatch_check_success(create_target[fabric][ObjectKind.NODEBATCH], ObjectState.STARTED,
                                               ObjectKind.PROCESSOR)
            ctx.obj.state = deepcopy(temp_state)
            ctx.obj.state.dump()
        if not processor_stop_batch:
            if processor_actions['stop']:
                log_info('Stopping processors: {0!r}'.format(processor_actions['stop']))
                res = temp_state.processor_stop(fabric, processor_actions['stop'])
                if not res[0]:
                    processor_stop_batch = True
                ctx.obj.state = deepcopy(temp_state)
                ctx.obj.state.dump()
            # Check if batches are finished
            temp_state.nodebatch_check_success(create_target[fabric][ObjectKind.NODEBATCH], ObjectState.STOPPED,
                                               ObjectKind.PROCESSOR)
            ctx.obj.state = deepcopy(temp_state)
            ctx.obj.state.dump()
        workload_stop_batch = False
        if not workload_stop_batch:
            if workload_actions['config']:
                log_info('Configuring workloads: {0!r}'.format(workload_actions['config']))
                res = temp_state.workload_configure(fabric, workload_actions['config'])
                if not res[0]:
                    workload_stop_batch = True
                ctx.obj.state = deepcopy(temp_state)
                ctx.obj.state.dump()
            # Check if batches are finished
            temp_state.nodebatch_check_success(create_target[fabric][ObjectKind.NODEBATCH], ObjectState.CONFIGURED,
                                               ObjectKind.WORKLOAD)
            ctx.obj.state = deepcopy(temp_state)
            ctx.obj.state.dump()
        if not workload_stop_batch:
            if workload_actions['start']:
                log_info('Starting workloads: {0!r}'.format(workload_actions['start']))
                res = temp_state.workload_start(fabric, workload_actions['start'])
                if not res[0]:
                    workload_stop_batch = True
                ctx.obj.state = deepcopy(temp_state)
                ctx.obj.state.dump()
            # Check if batches are finished
            temp_state.nodebatch_check_success(create_target[fabric][ObjectKind.NODEBATCH], ObjectState.STARTED,
                                               ObjectKind.WORKLOAD)
            ctx.obj.state = deepcopy(temp_state)
            ctx.obj.state.dump()
        if not workload_stop_batch:
            if workload_actions['stop']:
                log_info('Stopping workloads: {0!r}'.format(workload_actions['stop']))
                res = temp_state.workload_stop(fabric, workload_actions['stop'])
                if not res[0]:
                    workload_stop_batch = True
                ctx.obj.state = deepcopy(temp_state)
                ctx.obj.state.dump()
            # Check if batches are finished
            temp_state.nodebatch_check_success(create_target[fabric][ObjectKind.NODEBATCH], ObjectState.STOPPED,
                                               ObjectKind.WORKLOAD)
            ctx.obj.state = deepcopy(temp_state)
            ctx.obj.state.dump()
        # Check if there are failed operations
        if orch_stop_batch or processor_stop_batch or workload_stop_batch:
            batch_result_success = False
        # Ansible zone end
    if batch_result_success:
        log_ok('Batch is finished')
    else:
        log_error('Batch is finished')
    # Show grafana passwords
    if passwd_grafana is not None:
        ctx.obj.state.show_passwd(passwd_grafana, 'grafana')
    # Show controller passwords
    if passwd_controller is not None:
        ctx.obj.state.show_passwd(passwd_controller, 'controller')
    if not batch_result_success:
        sys.exit(1)
    return True


@create_cmd.command('fabric')
@click.pass_context
@click.argument('fabric-name')
def create_fabric(ctx, fabric_name):
    """Create fabric"""
    # Check if naming matches rules
    fabric_name = ctx.obj.state.normalise_state_obj_name('fabric', fabric_name)
    log_info('Creating fabric: {0}...'.format(fabric_name))
    # Generate temporary state
    temp_state = deepcopy(ctx.obj.state)
    # Chech if fabric exists
    if temp_state.check_fabric(fabric_name):
        obj = temp_state.get_fabric(fabric_name)
        if not temp_state.check_object_status(obj, ObjectStatus.FAILED) or \
                temp_state.check_object_state(obj, ObjectState.CONFIGURED):
            log_error("Cannot create {0!r}. Fabric already exists".format(fabric_name))
            sys.exit(1)
    else:
        obj = temp_state.get_clean_fabric()
        temp_state.add_fabric(fabric_name, obj)
    # Create fabric
    temp_state.set_object_state_status(obj, ObjectState.CREATED, ObjectStatus.SUCCESS)
    res = temp_state.fabric_create(fabric_name)
    if not res[0]:
        sys.exit(res[1])
    # Check if success
    if not temp_state.check_object_status(obj, ObjectStatus.FAILED):
        log_ok("Fabric {0!r} created successfully".format(fabric_name))
    # Dump state
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    return True


@create_cmd.command('orchestrator')
@click.pass_context
@click.argument('orchestrator-type', type=click.Choice(['controller', 'telemetry', 'events']))
@click.argument('vpc')
def create_orchestrator(ctx, vpc, orchestrator_type):
    """Create orchestrator"""
    obj_kind = ObjectKind.ORCHESTRATOR.value
    obj_char = 'c'
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error("Fabric should be set before")
        sys.exit(1)
    # Check if VPC exists
    if not ctx.obj.state.check_vpc(ctx.obj.state.get_current_fabric(), vpc):
        log_error("VPC doesn't exist")
        sys.exit(1)
    # Check for existing orch of same type in same fabric
    obj_list = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if
                orchestrator_type in x[1]['type'] and ctx.obj.state.check_object_status(x[-1], ObjectStatus.SUCCESS)]
    if obj_list:
        log_warn("Orchestrator of type {0} exists in current fabric, skipping...".format(orchestrator_type))
        sys.exit(1)

    # Check for existing
    obj_list = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if vpc in x[1]['vpc']]
    obj_index = 1
    if obj_list:
        obj_index = max(item[1]['index'] for item in obj_list)
        # Check if there is no node in created/failed state
        if not ctx.obj.state.check_object_state_status(obj_list[-1][1], ObjectState.CREATED, ObjectStatus.FAILED):
            obj_index = obj_index + 1
            obj_name = '{0!s}-{1!s}{2:02d}-{3!s}'.format(vpc.split("-")[0], obj_char, obj_index,
                                                         ctx.obj.state.get_current_fabric())
            obj_dns_enabled = 'false'
            log_info("Creating new {0} {1!r}...".format(obj_kind, obj_name))
        else:
            obj_name = '{0!s}-{1!s}{2:02d}-{3!s}'.format(vpc.split("-")[0], obj_char, obj_index,
                                                         ctx.obj.state.get_current_fabric())
            obj_dns_enabled = ctx.obj.state.get_fabric_object(obj_kind, obj_name)['properties']['dns_enabled']
            log_warn("There is failed {0} {1!r}. Trying to create again...".format(obj_kind, obj_name))
    else:
        obj_name = '{0!s}-{1!s}{2:02d}-{3!s}'.format(vpc.split("-")[0], obj_char, obj_index,
                                                     ctx.obj.state.get_current_fabric())
        obj_dns_enabled = 'false'
        log_info("Creating new {0} {1!r}...".format(obj_kind, obj_name))
    # Generate temporary state
    temp_state = deepcopy(ctx.obj.state)
    # Create state objects
    new_obj = temp_state.get_clean_orchestrator()
    new_obj['vpc'] = vpc
    new_obj['index'] = obj_index
    new_obj['type'] = orchestrator_type
    new_obj['properties']['dns_enabled'] = obj_dns_enabled
    temp_state.add_fabric_obj(temp_state.get_current_fabric(), obj_kind, obj_name, new_obj)
    # Get credentials
    credentials = Credentials(temp_state.get_current_fabric(), temp_state.get(), ctx.obj.state.config)
    if not credentials.get():
        log_error('Cannot create objects. Not able to get credentials')
        sys.exit(1)
    # Actual create
    if not temp_state.obj_create_check(temp_state.get_current_fabric(), {ObjectKind(obj_kind): [obj_name]}):
        sys.exit(1)
    res = temp_state.obj_create(temp_state.get_current_fabric(), {ObjectKind(obj_kind): [obj_name]}, credentials)
    # Dump state
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    if not res[0]:
        sys.exit(res[1])
    # Generate SSH configuration
    ssh_config = SshConfig(ctx.obj.state)
    if ssh_config.generate_config():
        log_info('Generating SSH config...')
    else:
        log_warn('Error during SSH config generation')
    return True


@create_cmd.command('processor')
@click.pass_context
@click.argument('vpc')
def create_processor(ctx, vpc):
    """Create processor"""
    obj_kind = ObjectKind.PROCESSOR.value
    obj_char = 'p'
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error("Fabric should be set before")
        sys.exit(1)
    # Check if VPC exists
    if not ctx.obj.state.check_vpc(ctx.obj.state.get_current_fabric(), vpc):
        log_error("VPC doesn't exist")
        sys.exit(1)
    # Check for existing
    obj_list = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if vpc in x[1]['vpc']]
    obj_index = 1
    if obj_list:
        obj_index = max(item[1]['index'] for item in obj_list)
        # Check if there is no node in created/failed state
        if not ctx.obj.state.check_object_state_status(obj_list[-1][1], ObjectState.CREATED, ObjectStatus.FAILED):
            obj_index = obj_index + 1
            obj_name = '{0!s}-{1!s}{2:02d}-{3!s}'.format(vpc.split("-")[0], obj_char, obj_index,
                                                         ctx.obj.state.get_current_fabric())
            obj_dns_enabled = 'false'
            log_info("Creating new {0} {1!r}...".format(obj_kind, obj_name))
        else:
            obj_name = '{0!s}-{1!s}{2:02d}-{3!s}'.format(vpc.split("-")[0], obj_char, obj_index,
                                                         ctx.obj.state.get_current_fabric())
            obj_dns_enabled = ctx.obj.state.get_fabric_object(obj_kind, obj_name)['properties']['dns_enabled']
            log_warn("There is failed {0} {1!r}. Trying to create again...".format(obj_kind, obj_name))
    else:
        obj_name = '{0!s}-{1!s}{2:02d}-{3!s}'.format(vpc.split("-")[0], obj_char, obj_index,
                                                     ctx.obj.state.get_current_fabric())
        obj_dns_enabled = 'false'
        log_info("Creating new {0} {1!r}...".format(obj_kind, obj_name))
    # Generate temporary state
    temp_state = deepcopy(ctx.obj.state)
    # Create state objects
    new_obj = temp_state.get_clean_processor()
    new_obj['vpc'] = vpc
    new_obj['index'] = obj_index
    new_obj['properties']['dns_enabled'] = obj_dns_enabled
    temp_state.add_fabric_obj(temp_state.get_current_fabric(), obj_kind, obj_name, new_obj)
    # Get credentials
    credentials = Credentials(temp_state.get_current_fabric(), temp_state.get(), ctx.obj.state.config)
    if not credentials.get():
        log_error('Cannot create objects. Not able to get credentials')
        sys.exit(1)
    # Actual create
    if not temp_state.obj_create_check(temp_state.get_current_fabric(), {ObjectKind(obj_kind): [obj_name]}):
        sys.exit(1)
    res = temp_state.obj_create(temp_state.get_current_fabric(), {ObjectKind(obj_kind): [obj_name]}, credentials)
    # Dump state
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    if not res[0]:
        sys.exit(res[1])
    # Generate SSH configuration
    ssh_config = SshConfig(ctx.obj.state)
    if ssh_config.generate_config():
        log_info('Generating SSH config...')
    else:
        log_warn('Error during SSH config generation')
    return True


@create_cmd.command('workload')
@click.pass_context
@click.argument('vpc')
@click.option('--os-type', type=click.Choice(['ubuntu', 'rhel']), required=False)
def create_workload(ctx, vpc, os_type):
    """Create workload"""
    obj_kind = ObjectKind.WORKLOAD.value
    obj_char = 'w'
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error("Fabric should be set before")
        sys.exit(1)
    # Check if VPC exists
    if not ctx.obj.state.check_vpc(ctx.obj.state.get_current_fabric(), vpc):
        log_error("VPC doesn't exist")
        sys.exit(1)
    # Check for existing
    obj_list = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if vpc in x[1]['vpc']]
    obj_index = 1
    if obj_list:
        obj_index = max(item[1]['index'] for item in obj_list)
        # Check if there is no node in created/failed state
        if not ctx.obj.state.check_object_state_status(obj_list[-1][1], ObjectState.CREATED, ObjectStatus.FAILED):
            obj_index = obj_index + 1
            obj_name = '{0!s}-{1!s}{2:02d}-{3!s}'.format(vpc.split("-")[0], obj_char, obj_index,
                                                         ctx.obj.state.get_current_fabric())
            obj_dns_enabled = 'false'
            log_info("Creating new {0} {1!r}...".format(obj_kind, obj_name))
        else:
            obj_name = '{0!s}-{1!s}{2:02d}-{3!s}'.format(vpc.split("-")[0], obj_char, obj_index,
                                                         ctx.obj.state.get_current_fabric())
            obj_dns_enabled = ctx.obj.state.get_fabric_object(obj_kind, obj_name)['properties']['dns_enabled']
            log_warn("There is failed {0} {1!r}. Trying to create again...".format(obj_kind, obj_name))
    else:
        obj_name = '{0!s}-{1!s}{2:02d}-{3!s}'.format(vpc.split("-")[0], obj_char, obj_index,
                                                     ctx.obj.state.get_current_fabric())
        obj_dns_enabled = 'false'
        log_info("Creating new {0} {1!r}...".format(obj_kind, obj_name))
    # Generate temporary state
    temp_state = deepcopy(ctx.obj.state)
    # Evaluate image OS type
    if os_type is None:
        os_type = ctx.obj.state.config.get_attr('os_type')
    # Create state objects
    new_obj = temp_state.get_clean_workload()
    new_obj['vpc'] = vpc
    new_obj['index'] = obj_index
    new_obj['properties']['dns_enabled'] = obj_dns_enabled
    new_obj['properties']['os_type'] = os_type
    temp_state.add_fabric_obj(temp_state.get_current_fabric(), obj_kind, obj_name, new_obj)
    # Get credentials
    credentials = Credentials(temp_state.get_current_fabric(), temp_state.get(), ctx.obj.state.config)
    if not credentials.get():
        log_error('Cannot create objects. Not able to get credentials')
        sys.exit(1)
    # Actual create
    if not temp_state.obj_create_check(temp_state.get_current_fabric(), {ObjectKind(obj_kind): [obj_name]}):
        sys.exit(1)
    res = temp_state.obj_create(temp_state.get_current_fabric(), {ObjectKind(obj_kind): [obj_name]}, credentials)
    # Dump state
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    if not res[0]:
        sys.exit(res[1])
    # Generate SSH configuration
    ssh_config = SshConfig(ctx.obj.state)
    if ssh_config.generate_config():
        log_info('Generating SSH config...')
    else:
        log_warn('Error during SSH config generation')
    return True


@create_cmd.command('vpc')
@click.pass_context
@click.argument('vpc-cloud', type=click.Choice(['azr', 'aws', 'gcp']))
@click.argument('vpc-region')
@click.option('--dry-run', required=False, is_flag=True, default=False, show_default=True)
def create_vpc(ctx, vpc_cloud, vpc_region, dry_run):
    obj_kind = ObjectKind.VPC.value
    """Create VPC"""
    # Check if fabric is set
    if not ctx.obj.state.get_current_fabric():
        log_error('Cannot create {}. Please select fabric first.'.format(obj_kind.upper()))
        sys.exit(1)
    # Check if cloud region is supported
    if vpc_region not in ctx.obj.cloud_regions[vpc_cloud]:
        log_error('Cannot create {}. Cloud region is not supported'.format(obj_kind.upper()))
        sys.exit(1)
    # Filter VPC list by cloud
    vpc_list = [x for x in ctx.obj.state.get_fabric_objects(obj_kind).items() if vpc_cloud in x[1]['cloud']]
    # Get max VPC index
    vpc_index = 1
    if vpc_list:
        vpc_index = max(item[1]['index'] for item in vpc_list) + 1
    obj_name = vpc_cloud + str(vpc_index) + '-vpc-' + ctx.obj.state.get_current_fabric()
    # Check if VPC already exist
    if ctx.obj.state.check_vpc(ctx.obj.state.get_current_fabric(), obj_name):
        log_error('Cannot create {}. {!r} already exist'.format(obj_kind.upper(), obj_name))
        sys.exit(1)
    # Create VPC
    log_info('Creating {}: {}...'.format(obj_kind.upper(), obj_name))
    if dry_run:
        log_warn('{} {!r} to be created (started with --dry-run)'.format(obj_kind.upper(), obj_name))
        return True
    # Generate temporary state
    temp_state = deepcopy(ctx.obj.state)
    # Create state objects
    new_obj = temp_state.get_clean_vpc()
    new_obj['cloud'] = vpc_cloud
    new_obj['region'] = vpc_region
    new_obj['index'] = vpc_index
    temp_state.add_fabric_obj(temp_state.get_current_fabric(), obj_kind, obj_name, new_obj)
    # Actual create
    res = temp_state.vpc_create(temp_state.get_current_fabric(), [obj_name])
    if not res[0]:
        sys.exit(res[1])
    # Dump state
    ctx.obj.state = deepcopy(temp_state)
    ctx.obj.state.dump()
    return True


if __name__ == "__main__":
    create_cmd()
