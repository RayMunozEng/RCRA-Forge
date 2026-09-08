#include "FurDenoiseLibrary.h"

#include "FurDenoiseViewExtension.h"
#include "HAL/IConsoleManager.h"

namespace
{
IConsoleVariable* GetDenoiseVariable()
{
    return IConsoleManager::Get().FindConsoleVariable(TEXT("r.FurAuthoring.Denoise"));
}
}

bool UFurDenoiseLibrary::SetRecoveredFurDenoiseEnabled(bool bEnabled)
{
    IConsoleVariable* Variable = GetDenoiseVariable();
    if (!Variable)
    {
        return false;
    }
    Variable->Set(bEnabled ? 1 : 0, ECVF_SetByCode);
    return Variable->GetInt() == (bEnabled ? 1 : 0);
}

bool UFurDenoiseLibrary::IsRecoveredFurDenoiseEnabled()
{
    const IConsoleVariable* Variable = GetDenoiseVariable();
    return Variable && Variable->GetInt() != 0;
}

bool UFurDenoiseLibrary::IsRecoveredFurDenoiseRegistered()
{
    return FurAuthoring::IsDenoiseViewExtensionRegistered();
}
