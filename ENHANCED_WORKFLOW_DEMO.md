# Enhanced Deployment Selection Workflow

## New Interactive Experience

When you run `python -m src.rancher_helm_exporter`, you'll now see:

```
+==============================================================================+
|                                                                              |
|    ####  ####    #   #### #### #   #     #   # ##### #     #   #            |
|   #     #   #   # #  #  # #  # #   #     #   # #     #     ## ##            |
|   # ##  ####   #####  ### ####  ###  --- ##### ####  #     # # #            |
|   #  #  # #    #   # #  # #  #   #       #   # #     #     #   #            |
|    ###  #  #   #   # #### ####   #       #   # ##### ##### #   #            |
|                                                                              |
|                         Kubernetes to Helm Chart Exporter                   |
|                                                                              |
|                     Transform your K8s workloads into                       |
|                        reusable Helm charts instantly!                      |
|                                                                              |
+==============================================================================+

>> Interactive Configuration
==================================================

Found existing configurations:
  1. previous-config-001
  2. Create new configuration

Select option [1-2]: 2

Configuration options:
  1. Auto-discover from deployments (recommended)
  2. Manual configuration

Select option [1-2]: 1

Kubernetes namespace to scan for deployments [default]: production

Scanning for deployments in namespace 'production'...

Found 5 deployment(s):
----------------------------------------------------------------------
#   Name                      Replicas   Images
----------------------------------------------------------------------
1   api-service               3/3        myregistry/api:v2.1.0
2   frontend-app              2/2        nginx:1.21, myapp/ui:v1.5.2
3   background-worker         1/1        myapp/worker:v3.0.1
4   notification-service      2/2        myapp/notifications:v1.2.0
5   user-management           3/3        myapp/users:v2.5.0
----------------------------------------------------------------------

Select deployment [1-5] or 'q' to quit: 2

Selected: frontend-app

Helm chart name [frontend-app]:
Output directory [./frontend-app-chart]:
Label selector (to include related resources) [app=frontend-app]:
Configure advanced options? [y/N]: n
Include secrets? [y/N]: n
Create test chart alongside main chart? [y/N]: y
Test suffix [test]:
Run helm lint after generation? [Y/n]:
Overwrite output directory if it exists? [y/N]: y
Save this configuration for future use? [Y/n]: y
Configuration name [config-20250919-1415]: frontend-config

Configuration saved: frontend-config

Creating Helm chart 'frontend-app'...
✅ Chart 'frontend-app' created successfully!

Would you like to create another chart from a different deployment? [y/N]: y

[Process repeats for another deployment...]

Configuration options:
  1. Auto-discover from deployments (recommended)
  2. Manual configuration

Select option [1-2]: 1

[Shows same deployment list...]

Select deployment [1-5] or 'q' to quit: 1

Selected: api-service
[... configuration process ...]

✅ Chart 'api-service' created successfully!

Would you like to create another chart from a different deployment? [y/N]: n

🎉 Successfully created 2 Helm chart(s):
  - frontend-app
  - api-service

You can now package and deploy these charts:
  helm package ./frontend-app-chart
  helm install frontend-app ./frontend-app-chart
  helm package ./api-service-chart
  helm install api-service ./api-service-chart
```

## Key Features Added

### 🚀 **Deployment Discovery**
- **Auto-scans namespace** for all deployments
- **Rich display table** showing replicas, images, status
- **Smart selection** with numbered menu

### 🎯 **Smart Configuration**
- **Auto-populates** chart name from deployment name
- **Suggests label selectors** based on deployment labels
- **Extracts app version** from container image tags
- **Pre-fills sensible defaults**

### 🔄 **Multi-Chart Workflow**
- **Create multiple charts** in one session
- **Track progress** with success indicators
- **Final summary** with deployment commands
- **Error handling** with option to continue

### 💾 **Enhanced Config Management**
- **Save configurations** for each deployment type
- **Reuse previous configs** from saved list
- **Smart naming** with timestamps

## Benefits

✅ **Zero guesswork** - See exactly what's available
✅ **Production-ready** - Extracts real values from live deployments
✅ **Batch processing** - Create multiple charts efficiently
✅ **Namespace-aware** - Works with restricted permissions
✅ **Error resilient** - Continues on failures, shows final results

This transforms the tool from a manual configuration process into an intelligent deployment discovery and chart generation workflow!