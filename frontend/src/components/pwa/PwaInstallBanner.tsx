'use client';

import React, { useState } from 'react';
import { usePwa } from '@/hooks/usePwa';
import { Button } from '@/components/ui/Button';
import { Download, Smartphone, Info, Share, MoreVertical } from 'lucide-react';

export function PwaInstallBanner() {
  const { isInstallable, isInstalled, promptInstall } = usePwa();
  const [showHelpModal, setShowHelpModal] = useState<boolean>(false);

  // Don't render anything if the app is already running as an installed PWA standalone app
  if (isInstalled) return null;

  return (
    <div className="bg-gradient-to-r from-sky-600 to-sky-700 text-white p-3.5 rounded-xl shadow-md space-y-3 mb-4">
      <div className="flex items-center justify-between space-x-3">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-white/20 rounded-lg shrink-0">
            <Smartphone className="w-5 h-5 text-white" />
          </div>
          <div>
            <h4 className="font-bold text-sm">Install GeoPresence PWA</h4>
            <p className="text-xs text-sky-100">Add to your phone or desktop home screen.</p>
          </div>
        </div>

        {isInstallable ? (
          <Button
            size="sm"
            onClick={promptInstall}
            className="bg-white text-sky-700 hover:bg-sky-50 border-none font-semibold shrink-0"
          >
            <Download className="w-3.5 h-3.5 mr-1.5" />
            Install App
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={() => setShowHelpModal(!showHelpModal)}
            className="bg-white/20 text-white hover:bg-white/30 border-none text-xs shrink-0"
          >
            <Info className="w-3.5 h-3.5 mr-1" />
            How to Install
          </Button>
        )}
      </div>

      {/* Manual Installation Instructions (for iOS Safari, Dev mode, or Chrome manual install) */}
      {(!isInstallable || showHelpModal) && (
        <div className="pt-2.5 border-t border-sky-500/50 text-xs text-sky-100 space-y-1.5 leading-relaxed">
          <div className="flex items-start space-x-2">
            <Share className="w-3.5 h-3.5 text-white shrink-0 mt-0.5" />
            <span>
              <strong>iOS (Safari):</strong> Tap <em>Share</em> icon → select <strong>"Add to Home Screen"</strong>.
            </span>
          </div>
          <div className="flex items-start space-x-2">
            <MoreVertical className="w-3.5 h-3.5 text-white shrink-0 mt-0.5" />
            <span>
              <strong>Android / Desktop (Chrome):</strong> Tap browser menu (⋮) → select <strong>"Install app"</strong> or <strong>"Add to Home Screen"</strong>.
            </span>
          </div>
          <p className="text-[11px] text-sky-200/90 italic pt-1">
            Note: 1-click automatic prompts activate in production builds over HTTPS or localhost.
          </p>
        </div>
      )}
    </div>
  );
}
